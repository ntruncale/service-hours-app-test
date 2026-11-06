import csv
import io
from datetime import timedelta
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from dashboard import queries
from hours.models import ApprovalRequest


def names(rows):
    return [r.student.first_name for r in rows]


def test_roster_filters(requirements, student9, student9b, approved):
    approved(student9, hours=Decimal("10"))
    assert names(queries.roster([9], "needs")) == ["Ben"]
    assert names(queries.roster([9], "done")) == ["Ana"]
    assert names(queries.roster([9], "none")) == ["Ben"]
    assert names(queries.roster([9], "behind")) == ["Ben"]
    assert sorted(names(queries.roster([9], "all"))) == ["Ana", "Ben"]


def test_roster_sorts_by_remaining(requirements, student9, student9b, approved):
    approved(student9, hours=Decimal("2"))
    assert names(queries.roster([9], sort="remaining")) == ["Ben", "Ana"]
    assert names(queries.roster([9], sort="approved")) == ["Ana", "Ben"]


def test_roster_search(requirements, student9, student9b):
    assert names(queries.roster([9], search="ben")) == ["Ben"]


def test_pending_hours_do_not_count(requirements, student9, make_entry):
    make_entry(student9, hours=Decimal("10"))
    row = queries.roster([9])[0]
    assert row.progress.approved == 0 and row.progress.pending == 10


def test_needs_hours_page(client, teacher9, requirements, student9, student9b, approved):
    approved(student9, hours=Decimal("12"))
    client.force_login(teacher9)
    page = client.get(reverse("dashboard:roster") + "?view=needs").content.decode()
    assert "Cho, Ben" in page and "Lee, Ana" not in page


def test_csv_export(client, teacher9, requirements, student9, approved):
    approved(student9, hours=Decimal("4"))
    client.force_login(teacher9)
    resp = client.get(reverse("dashboard:roster") + "?format=csv")
    assert resp["Content-Type"] == "text/csv"
    rows = list(csv.reader(io.StringIO(resp.content.decode())))
    assert rows[0][0] == "Last name"
    assert rows[1][:2] == ["Lee", "Ana"] and Decimal(rows[1][5]) == 4


def test_student_detail_and_override(client, teacher9, requirements, student9, make_entry):
    entry = make_entry(student9)
    client.force_login(teacher9)
    page = client.get(reverse("dashboard:student", args=[student9.pk]))
    assert b"Food Pantry" in page.content
    client.post(
        reverse("dashboard:entry_review", args=[entry.pk]), {"decision": "approve", "note": ""}
    )
    entry.refresh_from_db()
    assert entry.status == "pending"  # reason required
    client.post(
        reverse("dashboard:entry_review", args=[entry.pk]),
        {"decision": "approve", "note": "Called supervisor"},
    )
    entry.refresh_from_db()
    assert entry.status == "teacher_approved" and entry.reviewed_by == teacher9


def test_waiting_view(client, teacher9, student9, make_entry):
    old = make_entry(student9, organization="Old Org")
    make_entry(student9, organization="New Org")
    ApprovalRequest.objects.filter(entry=old).update(created_at=timezone.now() - timedelta(days=10))
    client.force_login(teacher9)
    page = client.get(reverse("dashboard:waiting")).content.decode()
    assert "Old Org" in page and "New Org" not in page
    page = client.get(reverse("dashboard:waiting") + "?all=1").content.decode()
    assert "New Org" in page


def test_flagged_view(client, teacher9, student9, make_entry):
    make_entry(student9, supervisor_name="Mom Lee", organization="Flag Org")
    make_entry(student9, organization="Clean Org")
    client.force_login(teacher9)
    page = client.get(reverse("dashboard:flagged")).content.decode()
    assert "Flag Org" in page and "Clean Org" not in page


def test_summary_and_orgs(client, teacher9, requirements, student9, student9b, approved):
    approved(student9, hours=Decimal("3"), organization="Food Pantry")
    approved(student9b, hours=Decimal("2"), organization="food pantry")
    client.force_login(teacher9)
    assert client.get(reverse("dashboard:summary")).status_code == 200
    orgs = list(queries.organizations([9]))
    assert len(orgs) == 1 and orgs[0]["hours"] == 5 and orgs[0]["students"] == 2
    assert b"Food Pantry" in client.get(reverse("dashboard:organizations")).content


def test_supervisor_lookup(client, teacher9, student9, student9b, make_entry):
    make_entry(student9, supervisor_email="same@org.test")
    make_entry(student9b, supervisor_email="same@org.test")
    client.force_login(teacher9)
    page = client.get(reverse("dashboard:supervisor") + "?email=same@org.test").content.decode()
    assert "2 entries" in page


def test_teacher_without_assignment(client, db):
    from accounts.models import User

    t = User.objects.create(username="x@school.test", email="x@school.test", role="teacher")
    client.force_login(t)
    assert b"aren't assigned" in client.get(reverse("dashboard:roster")).content
