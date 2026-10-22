"""Operators are created only by management tooling with an environment password (accounts decision d)."""
from io import StringIO
import os

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client

from account_helpers import make_customer, make_seller

pytestmark = pytest.mark.django_db


def run(*args):
    out = StringIO()
    call_command("create_operator", *args, stdout=out)
    return out.getvalue()


def test_creates_an_operator_from_the_environment_password_without_printing_it():
    output = run("ops-lead")
    user = get_user_model().objects.get(username="ops-lead")
    password = os.environ["DEMO_OPERATOR_PASSWORD"]
    assert user.role == "operator" and user.check_password(password)
    assert password not in output and "not printed" in output
    client = Client()
    assert client.post("/login/", {"username": "ops-lead", "password": password}).url == "/operator/"


def test_rerun_resets_the_password_without_a_duplicate(monkeypatch):
    run("ops-lead")
    monkeypatch.setenv("DEMO_OPERATOR_PASSWORD", "a-rotated-operator-secret-2026")
    run("ops-lead")
    assert get_user_model().objects.filter(username="ops-lead").count() == 1
    assert get_user_model().objects.get(username="ops-lead").check_password("a-rotated-operator-secret-2026")


@pytest.mark.parametrize("value", [None, "", "replace-demo-operator-password"])
def test_missing_or_placeholder_password_is_refused(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("DEMO_OPERATOR_PASSWORD", raising=False)
    else:
        monkeypatch.setenv("DEMO_OPERATOR_PASSWORD", value)
    with pytest.raises(CommandError, match="no fallback password"):
        run("ops-lead")
    assert not get_user_model().objects.filter(username="ops-lead").exists()


@pytest.mark.parametrize("make", [lambda: make_customer("taken"), lambda: make_seller("taken").user])
def test_an_existing_account_of_another_role_is_not_converted(make):
    user = make()
    role, password = user.role, user.password
    with pytest.raises(CommandError, match="was not converted"):
        run("taken")
    user.refresh_from_db()
    assert user.role == role and user.password == password


def test_the_password_cannot_be_passed_on_the_command_line():
    with pytest.raises(TypeError):
        call_command("create_operator", "ops-lead", password="on-the-command-line", stdout=StringIO())
    with pytest.raises(CommandError):
        call_command("create_operator", "ops-lead", "--password=on-the-command-line", stdout=StringIO())
    assert not get_user_model().objects.filter(username="ops-lead").exists()
