"""Every one of these is a real way a curious student could try to break in."""

import pytest
from django.urls import reverse

from hours.models import ServiceEntry


@pytest.mark.parametrize("name", ["hours:entry_edit", "hours:entry_delete", "hours:entry_resend"])
def test_student_cannot_touch_another_students_entry(client, student9, student9b, make_entry, name):
    entry = make_entry(student9b)
    client.force_login(student9)
    resp = client.post(reverse(name, args=[entry.pk]), {"hours": "12"})
    assert resp.status_code == 404
    assert ServiceEntry.objects.filter(pk=entry.pk, hours=3).exists()


@pytest.mark.parametrize(
    "url",
    [
        "/teacher/",
        "/teacher/waiting/",
        "/teacher/flagged/",
        "/teacher/summary/",
        "/teacher/organizations/",
        "/teacher/supervisor/",
    ],
)
def test_student_cannot_open_dashboard(client, student9, url):
    client.force_login(student9)
    assert client.get(url).status_code == 403


def test_student_cannot_open_student_detail(client, student9, student9b):
    client.force_login(student9)
    assert client.get(reverse("dashboard:student", args=[student9b.pk])).status_code == 403


def test_teacher_cannot_use_student_pages(client, teacher9):
    client.force_login(teacher9)
    assert client.get(reverse("hours:my_hours")).status_code == 403


def test_teacher_sees_only_their_grade(client, teacher9, student9, student12):
    client.force_login(teacher9)
    page = client.get(reverse("dashboard:roster")).content.decode()
    assert "Lee, Ana" in page and "Ruiz" not in page
    assert client.get(reverse("dashboard:student", args=[student12.pk])).status_code == 403


def test_teacher_cannot_widen_grade_by_query(client, teacher9, student12):
    client.force_login(teacher9)
    assert "Ruiz" not in client.get("/teacher/?grade=12").content.decode()


def test_teacher_cannot_override_other_grade(client, teacher9, student12, make_entry):
    entry = make_entry(student12)
    client.force_login(teacher9)
    resp = client.post(
        reverse("dashboard:entry_review", args=[entry.pk]), {"decision": "approve", "note": "sure"}
    )
    assert resp.status_code == 403
    entry.refresh_from_db()
    assert entry.status == "pending"


def test_admin_sees_all_grades(client, school_admin, student9, student12):
    client.force_login(school_admin)
    page = client.get(reverse("dashboard:roster")).content.decode()
    assert "Lee, Ana" in page and "Ruiz, Cal" in page


def test_dev_login_hidden_when_disabled(client, settings, db):
    settings.DEV_LOGIN_ENABLED = False
    assert client.get(reverse("accounts:dev_login")).status_code == 404


def test_review_redirect_cannot_leave_site(client, teacher9, student9, make_entry):
    entry = make_entry(student9)
    client.force_login(teacher9)
    resp = client.post(
        reverse("dashboard:entry_review", args=[entry.pk]),
        {"decision": "approve", "note": "ok", "next": "https://evil.test/"},
    )
    assert resp.url.startswith("/teacher/students/")
