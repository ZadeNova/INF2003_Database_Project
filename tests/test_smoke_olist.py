"""Keep the standard-library HTTP smoke check aligned with seeded role landings."""
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

from accounts.mixins import landing_url
from scripts.smoke_olist import DEMO_LOGINS


@pytest.mark.django_db(transaction=True)
def test_smoke_landing_paths_match_seed_demo_roles(imported):
    call_command("seed_demo", stdout=StringIO())
    assert {role for role, _, _ in DEMO_LOGINS} == {"customer", "seller", "operator"}
    for role, username, expected_path in DEMO_LOGINS:
        user = get_user_model().objects.get(username=username)
        assert user.role == role
        assert expected_path == landing_url(user)
