"""Database queries for the teacher dashboard, kept apart from the views so they can be tested."""

from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Count, DecimalField, Min, Q, Sum, Value
from django.db.models.functions import Coalesce, Lower, TruncMonth

from accounts import school_year
from accounts.models import User
from hours.models import Requirement, ServiceEntry
from hours.services import Progress, progress_for

ZERO = Value(Decimal("0"), output_field=DecimalField(max_digits=8, decimal_places=2))
VIEWS = {
    "all": "All students",
    "needs": "Still needs hours",
    "behind": "Behind pace",
    "none": "No entries this year",
    "done": "Complete",
}


def grad_years_for(grades: list[int]) -> list[int]:
    return [school_year.graduation_year_for_grade(g) for g in grades]


def students_in(grades: list[int]):
    return User.objects.filter(
        role=User.Role.STUDENT, is_active=True, graduation_year__in=grad_years_for(grades)
    )


def entries_in(grades: list[int]):
    return ServiceEntry.objects.filter(
        student__role=User.Role.STUDENT, student__graduation_year__in=grad_years_for(grades)
    ).select_related("student")


@dataclass
class RosterRow:
    student: User
    progress: Progress
    entries_this_year: int
    behind: bool

    @property
    def grade(self):
        return self.student.current_grade


def roster(grades: list[int], view: str = "all", search: str = "", sort: str = "remaining"):
    current = school_year.current_school_year()
    qs = students_in(grades).annotate(
        approved=Coalesce(
            Sum("entries__hours", filter=Q(entries__status__in=ServiceEntry.COUNTED)), ZERO
        ),
        pending=Coalesce(
            Sum("entries__hours", filter=Q(entries__status=ServiceEntry.Status.PENDING)), ZERO
        ),
        this_year=Coalesce(
            Sum(
                "entries__hours",
                filter=Q(entries__status__in=ServiceEntry.COUNTED, entries__school_year=current),
            ),
            ZERO,
        ),
        entries_this_year=Count("entries", filter=Q(entries__school_year=current)),
    )
    if search:
        qs = qs.filter(
            Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
            | Q(email__icontains=search)
        )

    table = Requirement.by_grade()
    elapsed = school_year.fraction_of_year_elapsed()
    rows = []
    for s in qs:
        p = progress_for(
            s, table=table, approved=s.approved, pending=s.pending, this_year=s.this_year
        )
        rows.append(
            RosterRow(s, p, s.entries_this_year, behind=not p.done and p.behind_pace(elapsed))
        )

    if view == "needs":
        rows = [r for r in rows if not r.progress.done]
    elif view == "behind":
        rows = [r for r in rows if r.behind]
    elif view == "none":
        rows = [r for r in rows if r.entries_this_year == 0]
    elif view == "done":
        rows = [r for r in rows if r.progress.done]

    sorters = {
        "remaining": lambda r: (-r.progress.remaining, r.student.last_name),
        "name": lambda r: (r.student.last_name.lower(), r.student.first_name.lower()),
        "approved": lambda r: (-r.progress.approved, r.student.last_name),
        "grade": lambda r: (r.grade or 0, r.student.last_name),
    }
    rows.sort(key=sorters.get(sort, sorters["remaining"]))
    return rows


def summary(grades: list[int]) -> dict:
    current = school_year.current_school_year()
    rows = roster(grades)
    per_grade = []
    for g in grades:
        g_rows = [r for r in rows if r.grade == g]
        done = sum(1 for r in g_rows if r.progress.done)
        per_grade.append(
            {
                "grade": g,
                "students": len(g_rows),
                "done": done,
                "percent_done": int(done / len(g_rows) * 100) if g_rows else 0,
                "behind": sum(1 for r in g_rows if r.behind),
                "hours": sum((r.progress.this_year for r in g_rows), Decimal("0")),
            }
        )

    counted = entries_in(grades).filter(status__in=ServiceEntry.COUNTED, school_year=current)
    by_month = list(
        counted.annotate(month=TruncMonth("service_date"))
        .values("month")
        .annotate(hours=Sum("hours"))
        .order_by("month")
    )
    labels = dict(ServiceEntry.Category.choices)
    by_category = [
        {"category": labels.get(c["category"], c["category"]), "hours": c["hours"]}
        for c in counted.values("category").annotate(hours=Sum("hours")).order_by("-hours")
    ]
    status_counts = dict(
        entries_in(grades).filter(school_year=current).values_list("status").annotate(n=Count("id"))
    )
    return {
        "per_grade": per_grade,
        "by_month": by_month,
        "by_category": by_category,
        "max_month": max((m["hours"] for m in by_month), default=0),
        "max_category": max((c["hours"] for c in by_category), default=0),
        "status_counts": status_counts,
        "year_label": school_year.school_year_label(current),
    }


def organizations(grades: list[int], year: int | None = None):
    qs = entries_in(grades).filter(status__in=ServiceEntry.COUNTED)
    if year:
        qs = qs.filter(school_year=year)
    return (
        qs.annotate(org=Lower("organization"))
        .values("org")
        .annotate(
            name=Min("organization"),
            hours=Sum("hours"),
            students=Count("student", distinct=True),
            entries=Count("id"),
        )
        .order_by("-hours")
    )
