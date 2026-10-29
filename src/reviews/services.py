"""PostgreSQL verifies ownership first; MongoDB owns every review field and summary."""

import logging

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, transaction
from django.http import Http404
from django.utils import timezone
from pymongo.errors import DuplicateKeyError
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern

from accounts.audit import set_audit_context
from accounts.models import User
from config import mongo
from orders.models import Order, OrderLine

from .ratings import summary_pipeline

logger = logging.getLogger("mercer.errors")
VISIBLE = {"taken_down": {"$ne": True}}
NEWEST = [("answered_at", -1), ("olist_review_id", -1), ("order_line_id", -1)]


def customer_line(actor, line_id):
    if actor.role != User.Role.CUSTOMER:
        raise PermissionDenied
    try:
        line = OrderLine.objects.select_related("order__checkout", "product").get(
            pk=line_id, order__checkout__customer=actor
        )
    except (OrderLine.DoesNotExist, ValueError, TypeError):
        raise Http404 from None
    if line.order.status != Order.Status.DELIVERED:
        raise ValidationError("Only delivered items can be reviewed.")
    return line


def _summary(database, session, product_id, before, after):
    stats = database.platform_stats.find_one({"_id": "bayesian"}, session=session)
    result = database.product_specs.update_one(
        {"_id": product_id}, summary_pipeline(stats, before, after), session=session
    )
    if result.matched_count != 1:
        raise ValidationError("Product specifications are unavailable. Try again later.")
    latest = list(database.reviews.find({"product_id": product_id, **VISIBLE}, session=session).sort(NEWEST).limit(5))
    database.product_specs.update_one({"_id": product_id}, {"$set": {"latest_reviews": latest}}, session=session)


def _transact(client, callback):
    # with_transaction retries the whole callback on TransientTransactionError (including write conflicts),
    # and retries uncertain commits. No SQL writes or other side effects belong in the callback.
    with client.start_session() as session:
        return session.with_transaction(
            callback, read_concern=ReadConcern("snapshot"), write_concern=WriteConcern("majority")
        )


def write_review(actor, line_id, action, cleaned=None):
    line = customer_line(actor, line_id)
    if action not in {"create", "edit", "delete"}:
        raise Http404
    if action != "delete" and (not cleaned or type(cleaned.get("score")) is not int or not 1 <= cleaned["score"] <= 5):
        raise ValidationError("Choose a score from 1 to 5.")
    with mongo.client() as client:
        database = client[mongo.database_name()]

        def change(session):
            before = database.reviews.find_one({"order_line_id": line.pk}, session=session)
            if action == "create" and before:
                raise ValidationError("This item already has a review. Edit it instead.")
            if action != "create" and (not before or before["customer_id"] != actor.pk):
                raise Http404
            after = None
            if action == "delete":
                database.reviews.delete_one({"order_line_id": line.pk, "customer_id": actor.pk}, session=session)
            else:
                now = timezone.now()
                after = {
                    **(before or {}),
                    "_id": line.pk,
                    "order_line_id": line.pk,
                    "order_id": line.order_id,
                    "checkout_id": line.order.checkout_id,
                    "product_id": line.product_id,
                    "seller_id": line.seller_id,
                    "customer_id": actor.pk,
                    "score": cleaned["score"],
                    "title_en": cleaned.get("title", ""),
                    "text_en": cleaned.get("text", ""),
                    "title_pt": "",
                    "text_pt": "",
                    "machine_translated": False,
                    "from_order_review": False,
                    "olist_review_id": None,
                    "created_at": (before or {}).get("created_at", now),
                    "answered_at": now,
                }
                if before:
                    database.reviews.replace_one({"order_line_id": line.pk}, after, session=session)
                else:
                    database.reviews.insert_one(after, session=session)
            _summary(database, session, line.product_id, before, after)
            return after

        try:
            return _transact(client, change)
        except DuplicateKeyError:
            raise ValidationError("This item already has a review. Edit it instead.") from None


def moderate_review(actor, line_id, action, reason):
    if actor.role != User.Role.OPERATOR:
        raise PermissionDenied
    if action not in {"takedown", "restore"}:
        raise Http404
    if not (reason or "").strip():
        raise ValidationError("Give a reason.")
    mongo_written = False
    try:
        with transaction.atomic():
            set_audit_context(actor.pk, reason.strip())
            # Narrow definer function: fixed table/actions, context actor/reason, no direct audit DML.
            with connection.cursor() as cursor:
                cursor.execute("SELECT public.audit_review_moderation(%s, %s)", [str(line_id), action])
            with mongo.client() as client:
                database = client[mongo.database_name()]

                def change(session):
                    before = database.reviews.find_one({"order_line_id": line_id}, session=session)
                    if before is None:
                        raise Http404
                    target = action == "takedown"
                    if bool(before.get("taken_down", False)) == target:
                        raise ValidationError("This review has already changed. Reload and try again.")
                    after = {**before, "taken_down": target, "takedown_reason": reason.strip() if target else ""}
                    database.reviews.replace_one({"order_line_id": line_id}, after, session=session)
                    _summary(database, session, before["product_id"], before, after)

                _transact(client, change)
                mongo_written = True
    except Exception:
        if mongo_written:
            logger.error("reviews.cross_store_commit_unconfirmed", extra={"fields": {"order_line_id": line_id}})
        raise
