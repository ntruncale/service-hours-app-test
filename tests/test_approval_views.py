from datetime import timedelta

import pytest
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from hours.models import ApprovalRequest, ServiceEntry


@pytest.fixture
def link(student9, make_entry, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        entry = make_entry(student9)
    url = mail.outbox[-1].body.split("https://hours.test", 1)[1].split()[0]
    return entry, url


def test_get_shows_entry_but_never_approves(client, link):
    entry, url = link
    resp = client.get(url)
    assert resp.status_code == 200
    assert b"Food Pantry" in resp.content
    entry.refresh_from_db()
    assert entry.status == ServiceEntry.Status.PENDING
    assert entry.approval_requests.get().opened_at is not None


def test_post_approve(client, link):
    entry, url = link
    resp = client.post(url, {"decision": "approve", "typed_name": "Maria Delgado", "comment": ""})
    assert resp.status_code == 200
    assert b"Thank you" in resp.content
    entry.refresh_from_db()
    assert entry.status == ServiceEntry.Status.APPROVED
    req = entry.approval_requests.get()
    assert req.supervisor_typed_name == "Maria Delgado"
    assert entry.audit.filter(
        action="supervisor approved", actor_label="maria@pantry.test"
    ).exists()


def test_link_works_only_once(client, link):
    entry, url = link
    client.post(url, {"decision": "approve", "typed_name": "Maria"})
    resp = client.post(url, {"decision": "decline", "typed_name": "Maria", "comment": "oops"})
    assert resp.status_code == 410
    entry.refresh_from_db()
    assert entry.status == ServiceEntry.Status.APPROVED


def test_decline_requires_comment(client, link):
    entry, url = link
    resp = client.post(url, {"decision": "decline", "typed_name": "Maria"})
    assert resp.status_code == 200 and b"why" in resp.content
    entry.refresh_from_db()
    assert entry.status == ServiceEntry.Status.PENDING
    client.post(url, {"decision": "decline", "typed_name": "Maria", "comment": "Not here that day"})
    entry.refresh_from_db()
    assert entry.status == ServiceEntry.Status.DECLINED


def test_signature_required(client, link):
    entry, url = link
    client.post(url, {"decision": "approve", "typed_name": ""})
    entry.refresh_from_db()
    assert entry.status == ServiceEntry.Status.PENDING


def test_expired_link(client, link):
    entry, url = link
    ApprovalRequest.objects.filter(entry=entry).update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )
    assert client.get(url).status_code == 410
    client.post(url, {"decision": "approve", "typed_name": "Maria"})
    entry.refresh_from_db()
    assert entry.status == ServiceEntry.Status.PENDING


def test_replaced_link(client, link):
    entry, url = link
    ApprovalRequest.issue(entry)
    resp = client.get(url)
    assert resp.status_code == 410 and b"replaced" in resp.content


def test_unknown_token(client, db):
    assert client.get(reverse("hours:approve", args=["not-a-real-token"])).status_code == 404


def test_approval_page_shows_only_this_entry(client, link, student9, make_entry):
    entry, url = link
    make_entry(student9, organization="Secret Other Org")
    assert b"Secret Other Org" not in client.get(url).content


def test_rate_limit(client, db):
    url = reverse("hours:approve", args=["guess"])
    codes = [client.get(url).status_code for _ in range(31)]
    assert codes[-1] == 429
