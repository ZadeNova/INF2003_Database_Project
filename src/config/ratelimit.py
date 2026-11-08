"""Rate-limit policy for sign-in and review saving, and the 429 page (docs/plans/redis.md).

Strict per account, loose per address, because many people share one address (Docker, a school, a campus network):
- sign-in attempts per username and address are counted before the password is checked, in one atomic step, and cleared
  by a successful login;
- failed sign-ins per address are counted separately (a success never counts) and the limit is high;
- review saves per customer are counted only when a save succeeded.
The address is REMOTE_ADDR only (a forwarded header is spoofable); IPv6 addresses count as their /64 network. Usernames
are trimmed and Unicode-normalised (as the login form does, case kept) before hashing, and a name that does not exist counts like any other,
so the 429 reveals nothing about accounts. If Redis cannot be used every check says "allowed" (fail open).
"""

import ipaddress
import unicodedata
from dataclasses import dataclass
from math import ceil

from django.conf import settings
from django.http import HttpResponse
from django.template.loader import render_to_string

from config import redis_store


def client_address(request):
    raw = request.META.get("REMOTE_ADDR", "")
    try:
        address = ipaddress.ip_address(raw)
    except ValueError:
        return "unknown"
    if address.version == 6:
        if address.ipv4_mapped is not None:
            return str(address.ipv4_mapped)
        return str(ipaddress.ip_network(f"{address}/64", strict=False))
    return str(address)


def normalise_username(value):
    """The name as Django will authenticate it: NFKC-normalised and stripped, as the login form does.

    Case is deliberately kept. Django matches usernames exactly, so "Jessica" is not the account "jessica"; folding case
    would only let look-alike names (such as "jeßica", which folds to "jessica") share, and so reset, one counter.
    """
    return unicodedata.normalize("NFKC", value or "").strip()[:150]


def retry_text(seconds):
    return "less than a minute" if seconds <= 60 else f"about {ceil(seconds / 60)} minutes"


def too_many_requests(retry_after, *, back_url="/", back_label="Back to the shop"):
    """The 429 page. Rendered without a request so it never touches the user or session (it must work during an outage)."""
    html = render_to_string(
        "429.html",
        {
            "retry_after": retry_after,
            "retry_text": retry_text(retry_after),
            "back_url": back_url,
            "back_label": back_label,
        },
    )
    response = HttpResponse(html, status=429)
    response["Retry-After"] = str(retry_after)
    response["Cache-Control"] = "no-store"
    return response


@dataclass(frozen=True)
class LoginAttempt:
    subject: str
    address: str
    retry_after: int  # 0 when the attempt may go ahead

    @property
    def blocked(self):
        return self.retry_after > 0


def start_login(request):
    """Count this sign-in attempt, or report how long the sender must wait."""
    address = client_address(request)
    subject = f"{normalise_username(request.POST.get('username', ''))}|{address}"
    ip_limit, ip_seconds = settings.RATE_LIMITS["login_ip"]
    by_address = redis_store.window_check("login_ip", address, ip_limit, ip_seconds)
    if not by_address.allowed:
        return LoginAttempt(subject, address, by_address.retry_after)
    limit, seconds = settings.RATE_LIMITS["login"]
    pair = redis_store.window_hit("login", subject, limit, seconds)
    return LoginAttempt(subject, address, 0 if pair.allowed else pair.retry_after)


def login_succeeded(attempt):
    redis_store.window_clear("login", attempt.subject)


def login_failed(attempt):
    limit, seconds = settings.RATE_LIMITS["login_ip"]
    redis_store.window_record("login_ip", attempt.address, limit, seconds)


def review_wait(user):
    """Seconds a customer must wait before saving another review; 0 when allowed."""
    limit, seconds = settings.RATE_LIMITS["review"]
    window = redis_store.window_check("review", str(user.pk), limit, seconds)
    return 0 if window.allowed else window.retry_after


def review_saved(user):
    limit, seconds = settings.RATE_LIMITS["review"]
    redis_store.window_record("review", str(user.pk), limit, seconds)
