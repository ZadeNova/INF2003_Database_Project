from .services import unseen_count


def alerts_badge(request):
    user = getattr(request, "user", None)
    return {
        "restock_unseen": unseen_count(user) if user and user.is_authenticated and user.role == "customer" else None
    }
