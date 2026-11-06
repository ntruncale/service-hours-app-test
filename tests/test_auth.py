from unittest import mock

import pytest
from django.urls import reverse

from accounts.models import User
from accounts.views import user_from_claims

TENANT = "11111111-2222-3333-4444-555555555555"


@pytest.fixture(autouse=True)
def ms_settings(settings):
    settings.MS_TENANT_ID = TENANT
    settings.MS_CLIENT_ID = "client"
    settings.MS_CLIENT_SECRET = "secret"
    settings.TEACHER_EMAILS = ["teach@school.test"]
    settings.ADMIN_EMAILS = ["boss@school.test"]


def claims(**kw):
    base = {
        "oid": "oid-1",
        "tid": TENANT,
        "preferred_username": "Kid@Students.School.test",
        "name": "Kid Person",
    }
    base.update(kw)
    return base


def test_login_redirects_to_microsoft(client, db):
    with mock.patch(
        "accounts.microsoft.start_flow",
        return_value={"auth_uri": "https://login.microsoftonline.com/x", "state": "s"},
    ):
        resp = client.get(reverse("accounts:microsoft_login"))
    assert resp.url.startswith("https://login.microsoftonline.com/")
    assert client.session["ms_auth_flow"]["state"] == "s"


def _callback(client, result):
    session = client.session
    session["ms_auth_flow"] = {"state": "s"}
    session.save()
    with mock.patch("accounts.microsoft.finish_flow", return_value=result):
        return client.get(reverse("accounts:microsoft_callback") + "?code=abc&state=s")


def test_callback_creates_student(client, db):
    resp = _callback(client, {"id_token_claims": claims()})
    assert resp.url == "/"
    user = User.objects.get(ms_oid="oid-1")
    assert user.email == "kid@students.school.test" and user.role == "student"
    assert user.first_name == "Kid" and not user.has_usable_password()
    # graduation year is still unknown, so the student is sent to onboarding next
    assert client.get("/my-hours/").url == reverse("accounts:onboarding")


def test_callback_rejects_other_tenant(client, db):
    resp = _callback(client, {"id_token_claims": claims(tid="someone-else")})
    assert resp.url == reverse("accounts:login")
    assert not User.objects.exists()


def test_callback_error(client, db):
    resp = _callback(client, {"error": "access_denied", "error_description": "nope"})
    assert resp.url == reverse("accounts:login")


def test_callback_without_flow(client, db):
    assert client.get(reverse("accounts:microsoft_callback")).url == reverse("accounts:login")


def test_callback_bad_state(client, db):
    session = client.session
    session["ms_auth_flow"] = {"state": "s"}
    session.save()
    with mock.patch("accounts.microsoft.finish_flow", side_effect=ValueError("state mismatch")):
        resp = client.get(reverse("accounts:microsoft_callback") + "?state=wrong")
    assert resp.url == reverse("accounts:login")


def test_roles_from_settings(db):
    t = user_from_claims(claims(oid="t", preferred_username="teach@school.test"))
    a = user_from_claims(claims(oid="a", preferred_username="boss@school.test"))
    assert t.role == "teacher" and not t.is_staff
    assert a.role == "admin" and a.is_staff and a.is_superuser


def test_links_precreated_user_by_email(db):
    pre = User.objects.create(
        username="teach2@school.test", email="teach2@school.test", role="teacher", first_name="Pre"
    )
    user = user_from_claims(claims(oid="new-oid", preferred_username="teach2@school.test"))
    assert user.pk == pre.pk and user.ms_oid == "new-oid" and user.role == "teacher"


def test_same_oid_new_email_keeps_account(db):
    first = user_from_claims(claims())
    again = user_from_claims(claims(preferred_username="renamed@students.school.test"))
    assert first.pk == again.pk and again.email == "renamed@students.school.test"


def test_logout_requires_post(client, student9):
    client.force_login(student9)
    assert client.get(reverse("accounts:logout")).status_code == 405
    client.post(reverse("accounts:logout"))
    assert client.get("/my-hours/").status_code == 302


def test_dev_login(client, settings, student9):
    settings.DEV_LOGIN_ENABLED = True
    assert b"Ana Lee" in client.get(reverse("accounts:dev_login")).content
    client.post(reverse("accounts:dev_login"), {"user_id": student9.pk})
    assert client.get("/my-hours/").status_code == 200
