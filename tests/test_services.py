from datetime import date, timedelta
from decimal import Decimal

from django.core import mail
from django.utils import timezone

from hours import services
from hours.models import ApprovalRequest, ServiceEntry


def test_submit_emails_supervisor(student9, make_entry, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        entry = make_entry(student9)
    assert entry.status == ServiceEntry.Status.PENDING
    assert len(mail.outbox) == 1
    msg = mail.outbox[0]
    assert msg.to == ["maria@pantry.test"]
    assert "Ana Lee" in msg.subject
    assert "https://hours.test/approve/" in msg.body
    assert msg.reply_to == [student9.email]
    assert entry.audit.filter(action="submitted").exists()


def test_flags(student9, make_entry):
    e = make_entry(student9, supervisor_name="Jo Lee", hours=Decimal("8"))
    assert any("same last name" in f for f in e.flags)
    e2 = make_entry(student9, hours=Decimal("6"))  # 14 hours on the same day
    assert any("hours logged on one day" in f for f in e2.flags)


def test_flag_school_address(student9, make_entry, settings):
    settings.BLOCKED_SUPERVISOR_DOMAINS = []
    e = make_entry(student9, supervisor_email="coach@students.school.test")
    assert any("school address" in f for f in e.flags)


def test_supervisor_decision_updates_entry_and_notifies(
    student9, make_entry, django_capture_on_commit_callbacks
):
    entry = make_entry(student9)
    req = entry.approval_requests.get()
    with django_capture_on_commit_callbacks(execute=True):
        services.record_supervisor_decision(
            req, approve=True, typed_name="Maria D", comment="Great"
        )
    entry.refresh_from_db()
    assert entry.status == ServiceEntry.Status.APPROVED
    assert mail.outbox[-1].to == [student9.email]
    assert "approved" in mail.outbox[-1].subject


def test_teacher_decision_requires_note(student9, teacher9, make_entry):
    entry = make_entry(student9)
    import pytest

    with pytest.raises(ValueError):
        services.teacher_decision(entry, teacher=teacher9, approve=True, note="  ")
    services.teacher_decision(entry, teacher=teacher9, approve=True, note="Phoned supervisor")
    entry.refresh_from_db()
    assert entry.status == ServiceEntry.Status.TEACHER_APPROVED
    assert entry.reviewed_by == teacher9
    assert not entry.approval_requests.filter(revoked=False, responded_at__isnull=True).exists()


def test_progress(student9, requirements, approved, make_entry):
    approved(student9, hours=Decimal("4"))
    approved(student9, hours=Decimal("2.5"))
    make_entry(student9, hours=Decimal("1"))  # pending, doesn't count
    p = services.progress_for(student9)
    assert p.approved == Decimal("6.5")
    assert p.pending == Decimal("1")
    assert p.required == 10
    assert p.remaining == Decimal("3.5")
    assert p.percent == 65
    assert not p.done


def test_progress_senior_needs_all_four_years(student12, requirements, approved):
    approved(student12, hours=Decimal("10"), service_date=date(2024, 3, 1))
    p = services.progress_for(student12)
    assert p.required == 40 and p.remaining == 30


def test_behind_pace(student9, requirements):
    p = services.progress_for(student9)
    assert p.behind_pace(0.5)  # 0 of 5 expected by mid-year
    assert not p.behind_pace(0.0)


def test_reminders_then_expiry(student9, make_entry, settings):
    settings.REMINDER_AFTER_DAYS = [4, 9]
    settings.APPROVAL_LINK_DAYS = 14
    entry = make_entry(student9)
    first = entry.approval_requests.get()
    mail.outbox.clear()
    now = timezone.now()

    assert services.process_reminders(now + timedelta(days=2)) == {"reminded": 0, "expired": 0}
    assert services.process_reminders(now + timedelta(days=5)) == {"reminded": 1, "expired": 0}
    assert "Reminder" in mail.outbox[-1].subject
    # Running again the same day does not send a second reminder
    assert services.process_reminders(now + timedelta(days=5))["reminded"] == 0
    assert services.process_reminders(now + timedelta(days=10))["reminded"] == 1
    assert services.process_reminders(now + timedelta(days=15)) == {"reminded": 0, "expired": 1}
    entry.refresh_from_db()
    first.refresh_from_db()
    assert entry.status == ServiceEntry.Status.EXPIRED
    assert first.revoked
    assert not ApprovalRequest.objects.filter(entry=entry, revoked=False).exists()


def test_can_resend_once_an_hour(student9, make_entry):
    entry = make_entry(student9)
    assert not services.can_resend(entry)
    ApprovalRequest.objects.filter(entry=entry).update(
        created_at=timezone.now() - timedelta(hours=2)
    )
    assert services.can_resend(entry)
    entry.status = ServiceEntry.Status.APPROVED
    assert not services.can_resend(entry)
