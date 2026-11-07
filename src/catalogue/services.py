"""Seller writes keep PostgreSQL open until MongoDB accepts its own fields (catalogue decision c)."""

import logging

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import Http404
from gridfs import GridFS
from pymongo.errors import PyMongoError

from accounts.audit import set_audit_context
from accounts.models import Seller, User
from config import mongo
from reviews.ratings import empty_summary

from .models import Product

logger = logging.getLogger("mercer.errors")
PRODUCT_FIELDS = ("name", "category", "price", "stock", "freight", "lead_time_days")
# Fields other writers change while a seller has the form open: sales change stock.
CONCURRENT_FIELDS = ("stock", "price")


class StaleProductError(ValidationError):
    """The seller changed a field that someone else also changed while the form was open."""

    def __init__(self, message, live):
        super().__init__(message)
        self.live = live


def _merge_concurrent_edits(item, cleaned):
    """Compare-and-set per field, with the product row locked.

    A field the seller left as it was keeps its live value, so sales made meanwhile survive; a field the seller
    changed is applied only if nobody else changed it meanwhile. A form without the expected values applies as posted.
    """
    merged = dict(cleaned)
    for name in CONCURRENT_FIELDS:
        expected = cleaned.get("expected_" + name)
        if expected is None:
            continue
        live = getattr(item, name)
        if cleaned[name] == expected:
            merged[name] = live
        elif live != expected:
            raise StaleProductError(
                f"The {name} changed to {live} while you were editing. Check it and save again.",
                {"stock": item.stock, "price": item.price},
            )
    return merged


def _seller_lock(seller, actor):
    if actor.pk != seller.user_id or actor.role != User.Role.SELLER:
        raise PermissionDenied
    if not Seller.objects.select_for_update().filter(pk=seller.pk, status=Seller.Status.APPROVED).exists():
        raise PermissionDenied


def _editable(seller, pk):
    try:
        return Product.objects.select_for_update().get(pk=pk, seller=seller, taken_down=False)
    except Product.DoesNotExist:
        raise Http404 from None


def _delete_photo(database, file_id):
    if file_id:
        try:
            GridFS(database, collection="photos").delete(file_id)
        except PyMongoError:
            logger.error("catalogue.photo_cleanup_failed")


def save_product(seller, actor, cleaned, *, pk=None):
    new_photo = old_photo = None
    database = None
    mongo_written = False
    item = None
    try:
        with transaction.atomic():
            set_audit_context(actor.pk, "Seller saved product")
            _seller_lock(seller, actor)
            item = _editable(seller, pk) if pk is not None else Product(seller=seller, has_generated_content=False)
            if pk is not None:
                cleaned = _merge_concurrent_edits(item, cleaned)
            for name in PRODUCT_FIELDS:
                setattr(item, name, cleaned[name])
            item.save()
            # The SQL write has happened. A real refused connection or write error here rolls it back.
            with mongo.client() as client:
                database = client[mongo.database_name()]
                previous = database.product_specs.find_one({"_id": item.pk})
                if pk is not None and previous is None:
                    raise ValidationError("Specifications are temporarily unavailable. Try again later.")
                old_photo = (previous or {}).get("photo_file_id")
                photo = cleaned.get("photo")
                if photo:
                    new_photo = GridFS(database, collection="photos").put(
                        photo.data, metadata={"content_type": photo.content_type, "product_id": item.pk}
                    )
                owned = {
                    "category_id": item.category_id,
                    "description": cleaned["description"],
                    "attributes": cleaned["attributes"],
                    "photo_file_id": new_photo or old_photo,
                    "has_generated_content": (previous or {}).get("has_generated_content", False),
                }
                if pk is None:
                    stats = database.platform_stats.find_one({"_id": "bayesian"})
                    database.product_specs.insert_one(
                        {"_id": item.pk, **owned, "latest_reviews": [], "rating_summary": empty_summary(stats)}
                    )
                else:
                    result = database.product_specs.update_one({"_id": item.pk}, {"$set": owned})
                    if result.matched_count != 1:
                        raise ValidationError("Specifications are temporarily unavailable. Try again later.")
                mongo_written = True
        # Delete the replaced file only after both stores accepted the save. A failed cleanup is logged.
        if new_photo and old_photo:
            _delete_photo(database, old_photo)
        return item
    except Exception:
        if mongo_written:
            logger.error("catalogue.cross_store_commit_unconfirmed", extra={"fields": {"product_id": item.pk}})
        elif new_photo is not None:
            _delete_photo(database, new_photo)
        raise


def deactivate_product(seller, actor, pk):
    with transaction.atomic():
        set_audit_context(actor.pk, "Seller deactivated product")
        _seller_lock(seller, actor)
        item = _editable(seller, pk)
        if item.active:
            item.active = False
            item.save(update_fields=["active"])
    return item


def moderate_product(actor, pk, action, reason):
    if actor.role != User.Role.OPERATOR:
        raise PermissionDenied
    if action not in {"takedown", "restore"}:
        raise Http404
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("Give a reason.")
    with transaction.atomic():
        set_audit_context(actor.pk, reason)
        item = Product.objects.select_for_update().get(pk=pk)
        target = action == "takedown"
        if item.taken_down == target:
            raise ValidationError("This product has already changed. Reload and try again.")
        item.taken_down = target
        item.taken_down_reason = reason if target else ""
        item.save(update_fields=["taken_down", "taken_down_reason"])
    return item
