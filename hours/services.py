"""Business rules for service entries. Views stay thin and call these functions."""

import logging
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Q, Sum
from django.urls import reverse
from django.utils import timezone

from accounts import school_year
from notifications.email import send_templated_email

from .models import ApprovalRequest, AuditLog, Requirement, ServiceEntry

log = logging.getLogger(__name__)
ZERO = Decimal("0")


def audit(entry, action, *, actor=None, actor_label="", detail="", ip=None):
    AuditLog.objects.create(
        entry=entry,
        actor=actor,
        actor_label=actor_label,
        action=action,
        detail=detail,
        ip_address=ip,
    )


# --- Flags -------------------------------------------------------------------


def compute_flags(entry: ServiceEntry) -> list[str]:
    """Reasons a teacher might want to double-check an entry. Flags never block a submission."""
    flags = []
    student = entry.student
    supervisor_last = (
        entry.supervisor_name.strip().split(" ")[-1].lower() if entry.supervisor_name else ""
    )
    if student.last_name and supervisor_last == student.last_name.lower():
        flags.append("Supervisor has the same last name as the student")

    same_day = (
        ServiceEntry.objects.filter(student=student, service_date=entry.service_date)
        .exclude(pk=entry.pk)
        .aggregate(total=Sum("hours"))["total"]
        or ZERO
    )
    if same_day + entry.hours > Decimal(str(settings.MAX_HOURS_PER_DAY)):
        flags.append(f"More than {settings.MAX_HOURS_PER_DAY:g} hours logged on one day")

    domain = entry.supervisor_email.rsplit("@", 1)[-1]
    student_domain = (student.email or "").rsplit("@", 1)[-1].lower()
    if student_domain and domain == student_domain:
        flags.append("Supervisor email is a school address; confirm it is a staff member")
    return flags


# --- Submitting and emailing --------------------------------------------------


def approval_url(raw_token: str) -> str:
    return settings.SITE_URL + reverse("hours:approve", args=[raw_token])


def _send_approval_email(entry: ServiceEntry, raw_token: str, reminder: bool = False):
    send_templated_email(
        to=[entry.supervisor_email],
        template="approval_request",
        context={
            "entry": entry,
            "student": entry.student,
            "url": approval_url(raw_token),
            "reminder": reminder,
            "days": settings.APPROVAL_LINK_DAYS,
        },
        reply_to=[entry.student.email] if entry.student.email else None,
    )


@transaction.atomic
def submit_entry(entry: ServiceEntry, *, actor=None) -> ApprovalRequest:
    """Save a new or edited entry as pending and email a fresh link to the supervisor."""
    is_new = entry.pk is None
    entry.status = ServiceEntry.Status.PENDING
    entry.reviewed_by = None
    entry.review_note = ""
    entry.save()
    entry.flags = compute_flags(entry)
    entry.save(update_fields=["flags"])
    req, raw = ApprovalRequest.issue(entry)
    audit(entry, "submitted" if is_new else "edited and resubmitted", actor=actor or entry.student)
    transaction.on_commit(lambda: _send_approval_email(entry, raw))
    return req


@transaction.atomic
def resend(entry: ServiceEntry, *, actor) -> ApprovalRequest:
    entry.status = ServiceEntry.Status.PENDING
    entry.save(update_fields=["status", "updated_at"])
    req, raw = ApprovalRequest.issue(entry)
    audit(entry, "link resent", actor=actor, detail=f"to {entry.supervisor_email}")
    transaction.on_commit(lambda: _send_approval_email(entry, raw))
    return req


def can_resend(entry: ServiceEntry) -> bool:
    """Limit resends to one per hour so a student can't spam a supervisor."""
    if entry.status not in (ServiceEntry.Status.PENDING, ServiceEntry.Status.EXPIRED):
        return False
    last = entry.approval_requests.first()
    return last is None or timezone.now() - last.created_at > timedelta(hours=1)


# --- Decisions ------------------------------------------------------------------


@transaction.atomic
def record_supervisor_decision(
    req: ApprovalRequest, *, approve: bool, typed_name: str, comment: str, ip=None
) -> None:
    req = ApprovalRequest.objects.select_for_update().get(pk=req.pk)
    if not req.is_usable:
        raise ValueError("This link can no longer be used.")
    entry = req.entry
    req.decision = req.Decision.APPROVED if approve else req.Decision.DECLINED
    req.supervisor_typed_name = typed_name.strip()
    req.supervisor_comment = comment.strip()
    req.responded_at = timezone.now()
    req.save()

    entry.status = ServiceEntry.Status.APPROVED if approve else ServiceEntry.Status.DECLINED
    entry.save(update_fields=["status", "updated_at"])
    audit(
        entry,
        "supervisor approved" if approve else "supervisor declined",
        actor_label=req.sent_to,
        detail=f"Signed: {req.supervisor_typed_name}. {req.supervisor_comment}".strip(),
        ip=ip,
    )
    transaction.on_commit(lambda: notify_student(entry, comment=req.supervisor_comment))


@transaction.atomic
def teacher_decision(entry: ServiceEntry, *, teacher, approve: bool, note: str) -> None:
    if not note.strip():
        raise ValueError("A reason is required.")
    entry.status = ServiceEntry.Status.TEACHER_APPROVED if approve else ServiceEntry.Status.DECLINED
    entry.reviewed_by = teacher
    entry.review_note = note.strip()
    entry.save()
    entry.approval_requests.filter(responded_at__isnull=True).update(revoked=True)
    audit(entry, "teacher approved" if approve else "teacher declined", actor=teacher, detail=note)
    transaction.on_commit(lambda: notify_student(entry, comment=note))


def notify_student(entry: ServiceEntry, comment: str = "") -> None:
    if not entry.student.email:
        return
    send_templated_email(
        to=[entry.student.email],
        template="student_decision",
        context={"entry": entry, "comment": comment, "url": settings.SITE_URL + reverse("home")},
    )


# --- Reminders and expiry (run daily) ----------------------------------------------


def process_reminders(now=None) -> dict[str, int]:
    """Send reminders on the configured days and expire old links. Safe to run repeatedly."""
    now = now or timezone.now()
    counts = {"reminded": 0, "expired": 0}
    open_requests = ApprovalRequest.objects.select_related("entry__student").filter(
        responded_at__isnull=True, revoked=False, entry__status=ServiceEntry.Status.PENDING
    )
    for req in open_requests:
        entry = req.entry
        if now >= req.expires_at:
            req.revoked = True
            req.save(update_fields=["revoked"])
            entry.status = ServiceEntry.Status.EXPIRED
            entry.save(update_fields=["status", "updated_at"])
            audit(entry, "link expired")
            counts["expired"] += 1
            continue

        age_days = (now - req.created_at).days
        due = [d for d in settings.REMINDER_AFTER_DAYS if age_days >= d]
        if len(due) > req.reminders_sent:
            # Reminders reuse the same link, so we must issue a new token to email it:
            # the raw token was never stored. The old link stops working.
            with transaction.atomic():
                reminders = req.reminders_sent + 1
                new_req, raw = ApprovalRequest.issue(entry)
                new_req.expires_at = req.expires_at
                new_req.created_at = req.created_at
                new_req.reminders_sent = reminders
                new_req.last_reminder_at = now
                new_req.save()
                audit(entry, "reminder sent", detail=f"reminder {reminders}")
            _send_approval_email(entry, raw, reminder=True)
            counts["reminded"] += 1
    return counts


# --- Progress -----------------------------------------------------------------------


@dataclass
class Progress:
    approved: Decimal
    pending: Decimal
    required: Decimal
    this_year: Decimal
    required_this_year: Decimal

    @property
    def remaining(self) -> Decimal:
        return max(self.required - self.approved, ZERO)

    @property
    def percent(self) -> int:
        if not self.required:
            return 100
        return min(100, int(self.approved / self.required * 100))

    @property
    def done(self) -> bool:
        return self.approved >= self.required

    def behind_pace(self, fraction_elapsed: float) -> bool:
        """Behind if approved hours are below earlier years' requirement plus this year's share."""
        expected = (self.required - self.required_this_year) + self.required_this_year * Decimal(
            str(round(fraction_elapsed, 3))
        )
        return self.approved < expected


def progress_for(student, *, table=None, approved=None, pending=None, this_year=None) -> Progress:
    table = table or Requirement.by_grade()
    grade = student.current_grade
    if approved is None:
        current = school_year.current_school_year()
        totals = student.entries.aggregate(
            approved=Sum("hours", filter=Q(status__in=ServiceEntry.COUNTED)),
            pending=Sum("hours", filter=Q(status=ServiceEntry.Status.PENDING)),
            this_year=Sum("hours", filter=Q(status__in=ServiceEntry.COUNTED, school_year=current)),
        )
        approved, pending, this_year = (
            totals[k] or ZERO for k in ("approved", "pending", "this_year")
        )
    return Progress(
        approved=approved or ZERO,
        pending=pending or ZERO,
        required=Requirement.required_through(grade, table),
        this_year=this_year or ZERO,
        required_this_year=table[grade] if grade else ZERO,
    )
