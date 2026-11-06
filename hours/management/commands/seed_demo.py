"""Fill the database with fake people and entries for testing. Never run in production."""

import random
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.test import override_settings
from django.utils import timezone

from accounts import school_year
from accounts.models import GradeAssignment, User
from hours import services
from hours.models import ApprovalRequest, AuditLog, Requirement, ServiceEntry

FIRST = [
    "Ava",
    "Liam",
    "Mia",
    "Noah",
    "Zoe",
    "Eli",
    "Maya",
    "Leo",
    "Ivy",
    "Owen",
    "Nora",
    "Jude",
    "Ruby",
    "Finn",
    "Lena",
    "Cole",
    "Sage",
    "Aria",
    "Max",
    "June",
    "Theo",
    "Elle",
    "Jace",
    "Wren",
]
LAST = [
    "Garcia",
    "Nguyen",
    "Patel",
    "Johnson",
    "Kim",
    "Okafor",
    "Rossi",
    "Silva",
    "Cohen",
    "Brown",
    "Haddad",
    "Lopez",
    "Murphy",
    "Chen",
    "Novak",
    "Diaz",
    "Ali",
    "Reyes",
    "Walsh",
    "Singh",
    "Moreau",
    "Fischer",
    "Park",
    "Ortiz",
]
ORGS = [
    ("Riverside Food Pantry", "food", "Maria Delgado"),
    ("Hope Animal Shelter", "animals", "Tom Becker"),
    ("Lincoln Elementary Reading Buddies", "tutoring", "Angela Price"),
    ("St. Mark Parish Festival", "faith", "Fr. Paul Ochoa"),
    ("City Parks Cleanup", "environment", "Dana Whitfield"),
    ("Sunrise Senior Living", "health", "Grace Lin"),
    ("Habitat Build Day", "events", "Marcus Hall"),
    ("School Open House Guides", "school", "Ms. Rivera"),
]


class Command(BaseCommand):
    help = "Create demo teachers, students and service entries (DEBUG only)."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete existing demo data first")

    def handle(self, *args, reset=False, **options):
        if not settings.DEBUG:
            raise CommandError("seed_demo only runs with DEBUG=true.")
        # Don't print a hundred fake emails to the terminal.
        with override_settings(EMAIL_BACKEND="django.core.mail.backends.dummy.EmailBackend"):
            with transaction.atomic():
                self._seed(reset)

    def _seed(self, reset):
        if reset:
            ServiceEntry.objects.all().delete()
            AuditLog.objects.all().delete()
            User.objects.filter(email__endswith="@example.org").delete()

        rng = random.Random(42)
        for grade, hours in ((9, 10), (10, 10), (11, 10), (12, 10)):
            Requirement.objects.update_or_create(
                grade_level=grade, defaults={"hours_required": Decimal(hours)}
            )

        admin = self._user("principal@example.org", "Pat", "Principal", User.Role.ADMIN)
        admin.is_staff = admin.is_superuser = True
        admin.save()
        for grade, (first, last) in zip(
            (9, 10, 11, 12),
            [("Helen", "Ward"), ("Omar", "Farouk"), ("Beth", "Carter"), ("Raj", "Mehta")],
            strict=True,
        ):
            teacher = self._user(
                f"{first.lower()}.{last.lower()}@example.org", first, last, User.Role.TEACHER
            )
            GradeAssignment.objects.get_or_create(teacher=teacher, grade_level=grade)

        today = school_year.today()
        names = [(f, la) for f in FIRST for la in LAST]
        rng.shuffle(names)
        idx = 0
        for grade in (9, 10, 11, 12):
            grad_year = school_year.graduation_year_for_grade(grade)
            freshman_start, _ = school_year.school_year_bounds(grad_year - 3)
            for _ in range(8):
                first, last = names[idx]
                idx += 1
                student = self._user(
                    f"{first.lower()}.{last.lower()}{grad_year % 100}@example.org",
                    first,
                    last,
                    User.Role.STUDENT,
                    grad_year,
                )
                self._entries(rng, student, grade, freshman_start, today)

        self.stdout.write(
            self.style.SUCCESS(
                f"Demo data ready: {User.objects.filter(role='student').count()} students, "
                f"{ServiceEntry.objects.count()} entries. Sign in at /accounts/dev-login/."
            )
        )

    def _user(self, email, first, last, role, grad_year=None):
        user, _ = User.objects.update_or_create(
            username=email,
            defaults={
                "email": email,
                "first_name": first,
                "last_name": last,
                "role": role,
                "graduation_year": grad_year,
            },
        )
        user.set_unusable_password()
        user.save()
        return user

    def _entries(self, rng, student, grade, start, today):
        profile = rng.choice(["none", "low", "mid", "high", "high"])
        count = {"none": 0, "low": 1, "mid": 3, "high": 2 + (grade - 9) * 3}[profile]
        span = max((today - start).days, 1)
        for _ in range(count):
            org, category, supervisor = rng.choice(ORGS)
            entry = ServiceEntry(
                student=student,
                service_date=start + timedelta(days=rng.randrange(span)),
                hours=Decimal(rng.choice([1, 1.5, 2, 2.5, 3, 4, 5, 6])),
                organization=org,
                location="Springfield",
                description="Helped with setup, served visitors, and cleaned up afterward.",
                category=category,
                supervisor_name=supervisor,
                supervisor_email=supervisor.lower().replace(".", "").replace(" ", ".")
                + "@example.net",
            )
            req = services.submit_entry(entry, actor=student)
            outcome = rng.random()
            age = rng.randrange(1, 20)
            ServiceEntry.objects.filter(pk=entry.pk).update(
                created_at=timezone.now() - timedelta(days=age)
            )
            ApprovalRequest.objects.filter(pk=req.pk).update(
                created_at=timezone.now() - timedelta(days=age)
            )
            if outcome < 0.7:
                services.record_supervisor_decision(
                    req, approve=True, typed_name=supervisor, comment="Thank you for helping!"
                )
            elif outcome < 0.78:
                services.record_supervisor_decision(
                    req,
                    approve=False,
                    typed_name=supervisor,
                    comment="I don't have a record of this date. Please check.",
                )
        if profile == "mid" and rng.random() < 0.4:
            # A suspicious one for the flagged view
            entry = ServiceEntry(
                student=student,
                service_date=today - timedelta(days=3),
                hours=Decimal("8"),
                organization="Family friend's yard work",
                location="Springfield",
                description="Raked leaves.",
                category="other",
                supervisor_name=f"Chris {student.last_name}",
                supervisor_email=f"chris.{student.last_name.lower()}@example.com",
            )
            services.submit_entry(entry, actor=student)
