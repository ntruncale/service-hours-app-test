"""Full-flow browser test at iPad size. Run with:  pytest -m e2e

Needs: pip install playwright  (and, on your own computer, `playwright install chromium`).
"""

import os

import pytest
from django.core import mail

os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")  # Playwright's sync API + Django DB
sync_api = pytest.importorskip("playwright.sync_api")

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]


@pytest.fixture
def browser():
    with sync_api.sync_playwright() as p:
        b = p.chromium.launch()
        yield p, b
        b.close()


def ipad_page(browser):
    p, b = browser
    return b.new_context(**p.devices["iPad (gen 7)"]).new_page()


def sign_in(page, base, name):
    page.goto(f"{base}/accounts/dev-login/")
    page.locator("tr", has_text=name).get_by_role("button", name="Sign in").click()


def test_student_to_supervisor_to_teacher(
    browser, live_server, settings, requirements, student9, teacher9
):
    settings.DEV_LOGIN_ENABLED = True
    base = live_server.url

    # 1. Student logs 10 hours
    student = ipad_page(browser)
    sign_in(student, base, "Ana Lee")
    student.get_by_role("link", name="+ Log service").click()
    student.fill("#id_service_date", "2026-10-10")
    student.fill("#id_hours", "10")
    student.fill("#id_organization", "Riverside Food Pantry")
    student.fill("#id_location", "Springfield")
    student.select_option("#id_category", "food")
    student.fill("#id_description", "Sorted donations")
    student.fill("#id_supervisor_name", "Maria Delgado")
    student.fill("#id_supervisor_email", "maria@pantry.test")
    student.get_by_role("button", name="Save and email supervisor").click()
    sync_api.expect(student.get_by_text("Waiting for supervisor").first).to_be_visible()

    # 2. Supervisor opens the emailed link in a fresh browser (no login) and approves
    assert mail.outbox[-1].to == ["maria@pantry.test"]
    path = "/approve/" + mail.outbox[-1].body.split("/approve/", 1)[1].split()[0]
    supervisor = ipad_page(browser)
    supervisor.goto(base + path)
    sync_api.expect(supervisor.get_by_text("Riverside Food Pantry")).to_be_visible()
    supervisor.fill("#id_typed_name", "Maria Delgado")
    supervisor.get_by_role("button", name="Approve these hours").click()
    sync_api.expect(supervisor.get_by_role("heading", name="Thank you")).to_be_visible()

    # 3. The student sees it approved
    student.reload()
    sync_api.expect(student.get_by_text("Approved by supervisor")).to_be_visible()

    # 4. The teacher no longer sees Ana under "Still needs hours"
    teacher = ipad_page(browser)
    sign_in(teacher, base, "Nina Nine")
    teacher.get_by_role("link", name="Still needs hours").click()
    sync_api.expect(teacher.get_by_text("No students match this view.")).to_be_visible()
    teacher.get_by_role("link", name="Complete").click()
    sync_api.expect(teacher.get_by_role("link", name="Lee, Ana")).to_be_visible()
