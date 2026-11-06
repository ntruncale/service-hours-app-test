from datetime import timedelta

from django.core import mail
from django.urls import reverse
from django.utils import timezone

from hours.models import ApprovalRequest, ServiceEntry

FORM = {
    "service_date": "2026-10-10",
    "hours": "2.5",
    "organization": "Animal Shelter",
    "location": "Springfield",
    "category": "animals",
    "description": "Walked dogs",
    "supervisor_name": "Sam Smith",
    "supervisor_email": "sam@shelter.test",
    "supervisor_phone": "",
}


def test_anonymous_redirected_to_login(client, db):
    resp = client.get(reverse("hours:my_hours"))
    assert resp.status_code == 302 and "/accounts/login/" in resp.url


def test_home_redirects_by_role(client, student9, teacher9):
    client.force_login(student9)
    assert client.get("/").url == reverse("hours:my_hours")
    client.force_login(teacher9)
    assert client.get("/").url == reverse("dashboard:roster")


def test_student_without_grad_year_must_onboard(client, student9):
    student9.graduation_year = None
    student9.save()
    client.force_login(student9)
    assert client.get(reverse("hours:my_hours")).url == reverse("accounts:onboarding")
    client.post(reverse("accounts:onboarding"), {"graduation_year": "2029"})
    student9.refresh_from_db()
    assert student9.graduation_year == 2029


def test_submit_entry(client, student9, django_capture_on_commit_callbacks):
    client.force_login(student9)
    with django_capture_on_commit_callbacks(execute=True):
        resp = client.post(reverse("hours:entry_new"), FORM)
    assert resp.status_code == 302
    entry = ServiceEntry.objects.get()
    assert entry.student == student9 and entry.status == "pending"
    assert mail.outbox[0].to == ["sam@shelter.test"]
    page = client.get(reverse("hours:my_hours"))
    assert b"Animal Shelter" in page.content and b"Waiting for supervisor" in page.content


def test_invalid_submission_shows_errors(client, student9):
    client.force_login(student9)
    resp = client.post(reverse("hours:entry_new"), {**FORM, "hours": "1.3"})
    assert resp.status_code == 200 and b"quarter hours" in resp.content
    assert not ServiceEntry.objects.exists()


def test_cannot_set_student_by_posting(client, student9, student9b):
    client.force_login(student9)
    client.post(reverse("hours:entry_new"), {**FORM, "student": student9b.pk})
    assert ServiceEntry.objects.get().student == student9


def test_edit_resubmits_with_new_link(client, student9, make_entry):
    entry = make_entry(student9)
    old = entry.approval_requests.get()
    client.force_login(student9)
    client.post(reverse("hours:entry_edit", args=[entry.pk]), {**FORM, "hours": "4"})
    entry.refresh_from_db()
    old.refresh_from_db()
    assert entry.hours == 4 and old.revoked
    assert entry.approval_requests.filter(revoked=False).count() == 1


def test_cannot_edit_or_delete_approved(client, student9, approved):
    entry = approved(student9)
    client.force_login(student9)
    client.post(reverse("hours:entry_edit", args=[entry.pk]), {**FORM, "hours": "9"})
    client.post(reverse("hours:entry_delete", args=[entry.pk]))
    entry.refresh_from_db()
    assert entry.hours == 3


def test_delete_pending(client, student9, make_entry):
    entry = make_entry(student9)
    client.force_login(student9)
    client.post(reverse("hours:entry_delete", args=[entry.pk]))
    assert not ServiceEntry.objects.filter(pk=entry.pk).exists()


def test_delete_requires_post(client, student9, make_entry):
    entry = make_entry(student9)
    client.force_login(student9)
    assert client.get(reverse("hours:entry_delete", args=[entry.pk])).status_code == 405


def test_resend(client, student9, make_entry, django_capture_on_commit_callbacks):
    entry = make_entry(student9)
    client.force_login(student9)
    client.post(reverse("hours:entry_resend", args=[entry.pk]))
    assert entry.approval_requests.count() == 1  # too soon
    ApprovalRequest.objects.update(created_at=timezone.now() - timedelta(hours=2))
    with django_capture_on_commit_callbacks(execute=True):
        client.post(reverse("hours:entry_resend", args=[entry.pk]))
    assert entry.approval_requests.count() == 2
    assert len(mail.outbox) == 1
