"""Retained security guarantees on the Phase 1A routes; later mutations remain closed."""
import pytest
from django.contrib.auth import get_user_model
from django.test import Client

pytestmark=pytest.mark.django_db


@pytest.mark.parametrize("role",["seller","operator"])
def test_registration_ignores_forged_role_staff_and_profile_fields(role):
    response=Client().post("/register/",{"username":"forged","password1":"Str0ngPass!2026","password2":"Str0ngPass!2026","role":role,"is_staff":"true","is_superuser":"true","seller_id":"1"})
    assert response.status_code == 302
    user=get_user_model().objects.get(username="forged")
    assert user.role == "customer" and not user.is_staff and not user.is_superuser


@pytest.mark.parametrize("route",["/login/","/register/","/logout/"])
def test_auth_mutations_require_csrf(route):
    client=Client(enforce_csrf_checks=True)
    response=client.post(route,{"username":"forged","password":"test"})
    assert response.status_code == 403 and not get_user_model().objects.exists()


def test_login_sql_injection_cannot_authenticate_or_change_an_account():
    user=get_user_model().objects.create_user(username="safe",password="Str0ngPass!2026")
    client=Client()
    response=client.post("/login/",{"username":"safe' OR 1=1 --","password":"irrelevant"})
    assert response.status_code == 200 and "_auth_user_id" not in client.session
    user.refresh_from_db()
    assert user.check_password("Str0ngPass!2026") and user.role == "customer"
