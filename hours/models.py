import hashlib
import secrets
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from accounts import school_year


class Requirement(models.Model):
    """Hours a student must earn during a grade level.

    Set 10 / 10 / 10 / 10 for a yearly requirement, or 0 / 0 / 0 / 40 for
    "40 hours any time before graduation". Progress is always measured against the
    total required through the student's current grade.
    """

    grade_level = models.PositiveSmallIntegerField(
        unique=True, choices=[(g, f"Grade {g}") for g in (9, 10, 11, 12)]
    )
    hours_required = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0"))

    class Meta:
        ordering = ["grade_level"]

    def __str__(self) -> str:
        return f"Grade {self.grade_level}: {self.hours_required} hours"

    @classmethod
    def by_grade(cls) -> dict[int, Decimal]:
        found = dict(cls.objects.values_list("grade_level", "hours_required"))
        return {g: found.get(g, Decimal("0")) for g in (9, 10, 11, 12)}

    @classmethod
    def required_through(cls, grade: int | None, table: dict[int, Decimal] | None = None):
        """Total hours required by the end of `grade`. None (graduated) means all four years."""
        table = table or cls.by_grade()
        last = 12 if grade is None else grade
        return sum((table[g] for g in range(9, last + 1)), Decimal("0"))


class ServiceEntry(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Waiting for supervisor"
        APPROVED = "approved", "Approved by supervisor"
        TEACHER_APPROVED = "teacher_approved", "Approved by teacher"
        DECLINED = "declined", "Declined"
        EXPIRED = "expired", "Link expired"

    COUNTED = (Status.APPROVED, Status.TEACHER_APPROVED)
    EDITABLE = (Status.PENDING, Status.DECLINED, Status.EXPIRED)

    class Category(models.TextChoices):
        TUTORING = "tutoring", "Tutoring / mentoring"
        FOOD = "food", "Food bank / meals"
        FAITH = "faith", "Faith community"
        ENVIRONMENT = "environment", "Environment / cleanup"
        HEALTH = "health", "Health / seniors"
        ANIMALS = "animals", "Animals"
        EVENTS = "events", "Community events"
        SCHOOL = "school", "School service"
        OTHER = "other", "Other"

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="entries"
    )
    service_date = models.DateField()
    hours = models.DecimalField(
        max_digits=5, decimal_places=2, validators=[MinValueValidator(Decimal("0.25"))]
    )
    organization = models.CharField(max_length=200)
    location = models.CharField(max_length=200)
    description = models.TextField(max_length=2000, help_text="What did you do?")
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.OTHER)

    supervisor_name = models.CharField(max_length=150)
    supervisor_email = models.EmailField()
    supervisor_phone = models.CharField(max_length=30, blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    school_year = models.PositiveIntegerField(editable=False)
    flags = models.JSONField(default=list, blank=True)

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_entries",
    )
    review_note = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-service_date", "-created_at"]
        verbose_name_plural = "service entries"

    def __str__(self) -> str:
        return f"{self.student} - {self.hours} h at {self.organization} on {self.service_date}"

    def save(self, *args, **kwargs):
        self.supervisor_email = (self.supervisor_email or "").strip().lower()
        if self.service_date:
            self.school_year = school_year.school_year_for(self.service_date)
        super().save(*args, **kwargs)

    @property
    def counts(self) -> bool:
        return self.status in self.COUNTED

    @property
    def is_editable(self) -> bool:
        return self.status in self.EDITABLE

    def clean(self):
        errors = {}
        today = school_year.today()

        if self.service_date and self.service_date > today:
            errors["service_date"] = "Service date can't be in the future."

        student = getattr(self, "student", None)
        if student and student.graduation_year and self.service_date:
            freshman_start, _ = school_year.school_year_bounds(student.graduation_year - 3)
            if self.service_date < freshman_start:
                errors["service_date"] = "Only service from freshman year onward counts."

        if self.hours is not None:
            if self.hours % Decimal("0.25") != 0:
                errors["hours"] = "Use quarter hours (for example 1.25, 1.5, 1.75)."
            elif self.hours > Decimal(str(settings.MAX_HOURS_PER_DAY)):
                errors["hours"] = f"One entry can be at most {settings.MAX_HOURS_PER_DAY:g} hours."

        email = (self.supervisor_email or "").lower()
        if email:
            domain = email.rsplit("@", 1)[-1]
            if student and email == (student.email or "").lower():
                errors["supervisor_email"] = "Enter your supervisor's email, not your own."
            elif domain in settings.BLOCKED_SUPERVISOR_DOMAINS:
                errors["supervisor_email"] = (
                    "Student email addresses can't be used for supervisors."
                )
            else:
                from accounts.models import User

                if User.objects.filter(email__iexact=email, role=User.Role.STUDENT).exists():
                    errors["supervisor_email"] = "A student can't be a supervisor."

        if errors:
            raise ValidationError(errors)


class ApprovalRequest(models.Model):
    """One emailed link to a supervisor. Only a hash of the token is stored."""

    class Decision(models.TextChoices):
        NONE = "", "No answer"
        APPROVED = "approved", "Approved"
        DECLINED = "declined", "Declined"

    entry = models.ForeignKey(
        ServiceEntry, on_delete=models.CASCADE, related_name="approval_requests"
    )
    token_hash = models.CharField(max_length=64, unique=True)
    sent_to = models.EmailField()
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    opened_at = models.DateTimeField(null=True, blank=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    revoked = models.BooleanField(default=False, help_text="Replaced by a newer link.")
    decision = models.CharField(max_length=10, choices=Decision.choices, blank=True)
    supervisor_typed_name = models.CharField(max_length=150, blank=True)
    supervisor_comment = models.TextField(blank=True, max_length=1000)
    reminders_sent = models.PositiveSmallIntegerField(default=0)
    last_reminder_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Approval request to {self.sent_to} for entry {self.entry_id}"

    @staticmethod
    def hash_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode()).hexdigest()

    @classmethod
    def issue(cls, entry: ServiceEntry) -> tuple["ApprovalRequest", str]:
        """Create a new link for `entry`, revoking any older unanswered ones."""
        entry.approval_requests.filter(responded_at__isnull=True, revoked=False).update(
            revoked=True
        )
        raw = secrets.token_urlsafe(32)
        req = cls.objects.create(
            entry=entry,
            token_hash=cls.hash_token(raw),
            sent_to=entry.supervisor_email,
            expires_at=timezone.now() + timedelta(days=settings.APPROVAL_LINK_DAYS),
        )
        return req, raw

    @classmethod
    def find(cls, raw_token: str) -> "ApprovalRequest | None":
        return (
            cls.objects.select_related("entry__student")
            .filter(token_hash=cls.hash_token(raw_token))
            .first()
        )

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    @property
    def is_usable(self) -> bool:
        return not (self.revoked or self.responded_at or self.is_expired)


class AuditLog(models.Model):
    entry = models.ForeignKey(
        ServiceEntry, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit"
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    actor_label = models.CharField(max_length=254, blank=True, help_text="e.g. supervisor email")
    action = models.CharField(max_length=40)
    detail = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        who = self.actor or self.actor_label or "system"
        return f"{self.created_at:%Y-%m-%d %H:%M} {who}: {self.action}"
