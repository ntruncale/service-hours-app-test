from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from hours.models import ApprovalRequest, Requirement, ServiceEntry


def entry_for(student, **overrides):
    data = dict(
        student=student,
        service_date=date(2026, 10, 1),
        hours=Decimal("2"),
        organization="Shelter",
        location="Town",
        description="Walked dogs",
        supervisor_name="Sam Smith",
        supervisor_email="sam@shelter.test",
    )
    data.update(overrides)
    return ServiceEntry(**data)


def errors(entry):
    with pytest.raises(ValidationError) as exc:
        entry.full_clean()
    return exc.value.message_dict


def test_valid_entry(student9):
    entry_for(student9).full_clean()


@pytest.mark.parametrize("hours", ["0", "-1", "1.3", "12.25", "30"])
def test_bad_hours(student9, hours):
    assert "hours" in errors(entry_for(student9, hours=Decimal(hours)))


@pytest.mark.parametrize("hours", ["0.25", "1.5", "12"])
def test_good_hours(student9, hours):
    entry_for(student9, hours=Decimal(hours)).full_clean()


def test_future_date_refused(student9):
    assert "service_date" in errors(entry_for(student9, service_date=date(2026, 11, 7)))


def test_before_freshman_year_refused(student9):
    # Class of 2030 starts freshman year July 1, 2026
    assert "service_date" in errors(entry_for(student9, service_date=date(2026, 6, 30)))
    entry_for(student9, service_date=date(2026, 7, 1)).full_clean()


def test_supervisor_cannot_be_self(student9):
    assert "supervisor_email" in errors(
        entry_for(student9, supervisor_email=student9.email.upper())
    )


def test_supervisor_cannot_use_student_domain(student9):
    assert "supervisor_email" in errors(
        entry_for(student9, supervisor_email="friend@students.school.test")
    )


def test_supervisor_cannot_be_another_student(student9, student9b, settings):
    settings.BLOCKED_SUPERVISOR_DOMAINS = []
    assert "supervisor_email" in errors(entry_for(student9, supervisor_email=student9b.email))


def test_school_year_and_email_normalized_on_save(student9):
    e = entry_for(student9, supervisor_email="  Sam@Shelter.TEST ")
    e.save()
    assert e.school_year == 2027
    assert e.supervisor_email == "sam@shelter.test"


def test_required_through(requirements):
    assert Requirement.required_through(9) == 10
    assert Requirement.required_through(11) == 30
    assert Requirement.required_through(None) == 40


def test_required_through_missing_rows_count_as_zero(db):
    Requirement.objects.create(grade_level=12, hours_required=40)
    assert Requirement.required_through(9) == 0
    assert Requirement.required_through(12) == 40


def test_token_is_stored_hashed(student9):
    e = entry_for(student9)
    e.save()
    req, raw = ApprovalRequest.issue(e)
    assert raw not in req.token_hash
    assert ApprovalRequest.find(raw) == req
    assert ApprovalRequest.find(raw + "x") is None
    assert len(raw) >= 40


def test_issue_revokes_older_links(student9):
    e = entry_for(student9)
    e.save()
    first, raw1 = ApprovalRequest.issue(e)
    second, _ = ApprovalRequest.issue(e)
    first.refresh_from_db()
    assert first.revoked and not first.is_usable
    assert second.is_usable
