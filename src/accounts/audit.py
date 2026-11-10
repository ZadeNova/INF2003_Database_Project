"""Audit context and the operator's seller status actions (accounts plan, P2 and P4).

The database writes the audit row: a trigger on accounts_seller reads the actor and reason set here. Both are
transaction-local, so they clear on commit or rollback and never leak to the next request on a reused connection.
"""

from django.core.exceptions import PermissionDenied
from django.db import connection, transaction

from .models import Seller, User

# action -> (expected current status, new status); mirrors the database transition trigger.
SELLER_ACTIONS = {
    "approve": (Seller.Status.PENDING, Seller.Status.APPROVED),
    "reject": (Seller.Status.PENDING, Seller.Status.REJECTED),
    "suspend": (Seller.Status.APPROVED, Seller.Status.SUSPENDED),
    "reinstate": (Seller.Status.SUSPENDED, Seller.Status.APPROVED),
}

# Every audit action the pages display: stored action code -> (label, badge tone). The codes stay the audit record's stable
# identifiers; only the label and tone are display. Tone None is neutral. DESIGN.md: red is never a status, so negative
# decisions stay neutral, and "warning" is the existing amber badge (there is no pending class).
AUDIT_ACTIONS = {
    "seller.approve": ("Approved", "completed"),
    "seller.reject": ("Rejected", None),
    "seller.suspend": ("Suspended", None),
    "seller.reinstate": ("Reinstated", "completed"),
    "product.create": ("Product created", "completed"),
    "product.update": ("Product updated", None),
    "product.activate": ("Product activated", "completed"),
    "product.deactivate": ("Product deactivated", None),
    "product.takedown": ("Product taken down", None),
    "product.restore": ("Product restored", "completed"),
    "order.paid": ("Paid", "warning"),
    "order.shipped": ("Shipped", "warning"),
    "order.delivered": ("Delivered", "completed"),
    "order.cancelled": ("Cancelled", None),
    "review.takedown": ("Review taken down", None),
    "review.restore": ("Review restored", "completed"),
}
AUDIT_LABELS = {code: label for code, (label, _) in AUDIT_ACTIONS.items()}
AUDIT_TONES = {code: tone for code, (_, tone) in AUDIT_ACTIONS.items() if tone}


class StaleAction(Exception):
    """The seller is no longer in the state the action expects (another operator acted first, or a repeat)."""


def set_audit_context(actor_id=None, reason=""):
    """Set both audit settings for the current transaction; empty strings mean absent (a system change)."""
    if not connection.in_atomic_block:
        raise RuntimeError("Audit context must be set inside transaction.atomic()")
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT set_config('mercer.actor_id', %s, true), set_config('mercer.audit_reason', %s, true)",
            ["" if actor_id is None else str(int(actor_id)), reason or ""],
        )


def allowed_actions(status):
    return [action for action, (expected, _) in SELLER_ACTIONS.items() if expected == status]


def change_seller_status(seller_id, action, actor, reason):
    """Apply one operator action atomically; raise StaleAction rather than write a second audit row."""
    expected, new = SELLER_ACTIONS[action]
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("A reason is required")
    if actor.role != User.Role.OPERATOR:  # defence in depth; views already require an operator
        raise PermissionDenied
    with transaction.atomic():
        seller = Seller.objects.select_for_update().get(pk=seller_id)
        if seller.status != expected:
            raise StaleAction(f"Seller is {seller.status}, not {expected}")
        set_audit_context(actor.pk, reason)
        Seller.objects.filter(pk=seller.pk).update(status=new)
        seller.status = new
    return seller
