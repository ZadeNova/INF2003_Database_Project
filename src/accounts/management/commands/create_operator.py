import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    help = (
        "Create an operator, or reset an existing operator's password, from DEMO_OPERATOR_PASSWORD. "
        "The password is never a command-line argument and is never printed."
    )

    def add_arguments(self, parser):
        parser.add_argument("username")

    def handle(self, *args, username, **options):
        password = os.environ.get("DEMO_OPERATOR_PASSWORD", "")
        if not password or password.startswith("replace-"):
            raise CommandError(
                "DEMO_OPERATOR_PASSWORD must be set to a generated value; there is no fallback password."
            )
        User = get_user_model()
        with transaction.atomic():
            user, created = User.objects.select_for_update().get_or_create(
                username=username, defaults={"role": User.Role.OPERATOR, "is_staff": True}
            )
            if user.role != User.Role.OPERATOR:
                raise CommandError(f"{username} already belongs to a {user.role} account; it was not converted.")
            user.set_password(password)
            user.save()
        verb = "Created" if created else "Updated the password of"
        self.stdout.write(f"{verb} operator {username}. The password was not printed.")
