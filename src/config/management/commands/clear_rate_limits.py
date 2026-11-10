from django.conf import settings
from django.core.management.base import BaseCommand

from config import redis_store


class Command(BaseCommand):
    help = (
        "Clear the Redis rate-limit counters (sign-in attempts and review saves). Useful on recording day: under Docker "
        "every client shares one address, so a few mistyped passwords can block the demo logins for 15 minutes."
    )

    def handle(self, *args, **options):
        if not settings.REDIS_ENABLED:
            self.stdout.write("Redis is disabled (REDIS_ENABLED=false); there are no counters to clear.")
            return
        removed = redis_store.delete_matching("limit:*")
        self.stdout.write(f"Cleared {removed} rate-limit counters.")
