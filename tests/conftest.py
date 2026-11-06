from datetime import date
from decimal import Decimal

import pytest
from django.core.cache import cache

from accounts import school_year
from accounts.models import GradeAssignment, User
from hours import services
from hours.models import Requirement, ServiceEntry

TODAY = date(2026, 11, 6)  # school year 2026-27 ("2027")


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(school_year, "today", lambda: TODAY)
    return TODAY


@pytest.fixture(autouse=True)
def _clean_cache(settings):
    cache.clear()
    settings.SITE_URL = "https://hours.test"
    settings.BLOCKED_SUPERVISOR_DOMAINS = ["students.school.test"]
    yield
    cache.clear()


@pytest.fixture
def requirements(db):
    for g in (9, 10, 11, 12):
        Requirement.objects.create(grade_level=g, hours_required=Decimal("10"))


def _user(email, first, last, role, grad_year=None):
    return User.objects.create(
        username=email,
        email=email,
        first_name=first,
        last_name=last,
        role=role,
        graduation_year=grad_year,
    )


@pytest.fixture
def student9(db):
    return _user("ana.lee30@students.school.test", "Ana", "Lee", User.Role.STUDENT, 2030)


@pytest.fixture
def student9b(db):
    return _user("ben.cho30@students.school.test", "Ben", "Cho", User.Role.STUDENT, 2030)


@pytest.fixture
def student12(db):
    return _user("cal.ruiz27@students.school.test", "Cal", "Ruiz", User.Role.STUDENT, 2027)


@pytest.fixture
def teacher9(db):
    t = _user("t9@school.test", "Nina", "Nine", User.Role.TEACHER)
    GradeAssignment.objects.create(teacher=t, grade_level=9)
    return t


@pytest.fixture
def teacher12(db):
    t = _user("t12@school.test", "Tom", "Twelve", User.Role.TEACHER)
    GradeAssignment.objects.create(teacher=t, grade_level=12)
    return t


@pytest.fixture
def school_admin(db):
    return _user("boss@school.test", "Pat", "Principal", User.Role.ADMIN)


@pytest.fixture
def make_entry(db):
    def make(student, *, submit=True, **overrides):
        data = {
            "service_date": date(2026, 10, 10),
            "hours": Decimal("3"),
            "organization": "Food Pantry",
            "location": "Springfield",
            "description": "Sorted cans",
            "category": "food",
            "supervisor_name": "Maria Delgado",
            "supervisor_email": "maria@pantry.test",
        }
        data.update(overrides)
        entry = ServiceEntry(student=student, **data)
        if submit:
            services.submit_entry(entry)
        else:
            entry.save()
        return entry

    return make


@pytest.fixture
def approved(make_entry):
    """Create an entry and mark it approved without going through email."""

    def make(student, **kw):
        entry = make_entry(student, **kw)
        entry.status = ServiceEntry.Status.APPROVED
        entry.save()
        return entry

    return make
