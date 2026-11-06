import csv
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Max
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from accounts import school_year
from accounts.decorators import staff_required
from accounts.models import User
from hours import services
from hours.models import ServiceEntry

from . import queries


def _grades(request) -> tuple[list[int], int | None]:
    """Grades the user may see, narrowed by ?grade= if given. Returns (grades, selected)."""
    visible = request.user.visible_grades()
    try:
        selected = int(request.GET.get("grade", ""))
    except ValueError:
        selected = None
    if selected in visible:
        return [selected], selected
    return visible, None


def _back(request, default: str):
    """Redirect to ?next= only if it points at this site (prevents open redirects)."""
    nxt = request.POST.get("next", "")
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
        return redirect(nxt)
    return redirect(default)


def _base_context(request, grades, selected, active):
    return {
        "visible_grades": request.user.visible_grades(),
        "selected_grade": selected,
        "grades": grades,
        "active": active,
        "year_label": school_year.school_year_label(school_year.current_school_year()),
    }


@staff_required
def roster(request):
    grades, selected = _grades(request)
    view = request.GET.get("view", "all")
    view = view if view in queries.VIEWS else "all"
    search = request.GET.get("q", "").strip()
    sort = request.GET.get("sort", "remaining")
    rows = queries.roster(grades, view=view, search=search, sort=sort) if grades else []

    if request.GET.get("format") == "csv":
        return _roster_csv(rows)

    context = _base_context(request, grades, selected, "roster")
    context.update(
        {
            "rows": rows,
            "view": view,
            "views": queries.VIEWS,
            "q": search,
            "sort": sort,
            "total_students": queries.students_in(grades).count() if grades else 0,
        }
    )
    return render(request, "dashboard/roster.html", context)


def _roster_csv(rows):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="service-hours.csv"'
    writer = csv.writer(response)
    writer.writerow(
        [
            "Last name",
            "First name",
            "Email",
            "Grade",
            "Class of",
            "Approved hours",
            "Pending hours",
            "Required to date",
            "Remaining",
            "Approved this year",
            "Behind pace",
        ]
    )
    for r in rows:
        s, p = r.student, r.progress
        writer.writerow(
            [
                s.last_name,
                s.first_name,
                s.email,
                r.grade,
                s.graduation_year,
                p.approved,
                p.pending,
                p.required,
                p.remaining,
                p.this_year,
                "yes" if r.behind else "no",
            ]
        )
    return response


def _visible_student(request, pk) -> User:
    student = get_object_or_404(User, pk=pk, role=User.Role.STUDENT)
    if not request.user.can_view_student(student):
        raise PermissionDenied
    return student


@staff_required
def student_detail(request, pk):
    student = _visible_student(request, pk)
    entries = student.entries.prefetch_related("approval_requests", "audit__actor").select_related(
        "reviewed_by"
    )
    years = {}
    for e in entries:
        bucket = years.setdefault(e.school_year, {"entries": [], "approved": 0})
        bucket["entries"].append(e)
        if e.counts:
            bucket["approved"] += e.hours
    context = _base_context(request, [], None, "roster")
    context.update(
        {
            "student": student,
            "progress": services.progress_for(student),
            "years": [
                (school_year.school_year_label(y), b)
                for y, b in sorted(years.items(), reverse=True)
            ],
            "print_mode": request.GET.get("print") == "1",
        }
    )
    return render(request, "dashboard/student_detail.html", context)


@staff_required
@require_POST
def entry_review(request, pk):
    entry = get_object_or_404(ServiceEntry, pk=pk)
    if not request.user.can_view_student(entry.student):
        raise PermissionDenied
    decision = request.POST.get("decision")
    note = request.POST.get("note", "")
    if decision not in ("approve", "decline"):
        messages.error(request, "Choose approve or decline.")
    elif not note.strip():
        messages.error(request, "Please give a reason; it is saved in the entry's history.")
    else:
        services.teacher_decision(
            entry, teacher=request.user, approve=decision == "approve", note=note
        )
        messages.success(request, "Entry updated and the student was notified.")
    return _back(request, reverse("dashboard:student", args=[entry.student_id]))


@staff_required
@require_POST
def entry_resend(request, pk):
    entry = get_object_or_404(ServiceEntry, pk=pk)
    if not request.user.can_view_student(entry.student):
        raise PermissionDenied
    if services.can_resend(entry):
        services.resend(entry, actor=request.user)
        messages.success(request, f"New link sent to {entry.supervisor_email}.")
    else:
        messages.error(request, "That entry was resent in the last hour or is not waiting.")
    return _back(request, reverse("dashboard:waiting"))


@staff_required
def waiting(request):
    grades, selected = _grades(request)
    show_all = request.GET.get("all") == "1"
    cutoff = timezone.now() - timedelta(days=settings.STALE_PENDING_DAYS)
    entries = (
        queries.entries_in(grades)
        .filter(status=ServiceEntry.Status.PENDING)
        .annotate(sent=Max("approval_requests__created_at"))
        .order_by("sent")
    )
    if not show_all:
        entries = entries.filter(sent__lt=cutoff)
    context = _base_context(request, grades, selected, "waiting")
    context.update(
        {"entries": entries, "show_all": show_all, "stale_days": settings.STALE_PENDING_DAYS}
    )
    return render(request, "dashboard/waiting.html", context)


@staff_required
def flagged(request):
    grades, selected = _grades(request)
    base = queries.entries_in(grades)
    context = _base_context(request, grades, selected, "flagged")
    context.update(
        {
            "flagged": base.exclude(flags=[]).exclude(status=ServiceEntry.Status.TEACHER_APPROVED),
            "declined": base.filter(status=ServiceEntry.Status.DECLINED).prefetch_related(
                "approval_requests"
            ),
        }
    )
    return render(request, "dashboard/flagged.html", context)


@staff_required
def summary(request):
    grades, selected = _grades(request)
    context = _base_context(request, grades, selected, "summary")
    context["summary"] = queries.summary(grades)
    return render(request, "dashboard/summary.html", context)


@staff_required
def organizations(request):
    grades, selected = _grades(request)
    all_years = request.GET.get("years") == "all"
    year = None if all_years else school_year.current_school_year()
    context = _base_context(request, grades, selected, "organizations")
    context.update({"orgs": queries.organizations(grades, year), "all_years": all_years})
    return render(request, "dashboard/organizations.html", context)


@staff_required
def supervisor_lookup(request):
    grades, selected = _grades(request)
    email = request.GET.get("email", "").strip().lower()
    entries = queries.entries_in(grades).filter(supervisor_email__icontains=email) if email else []
    context = _base_context(request, grades, selected, "supervisor")
    context.update({"email": email, "entries": entries})
    return render(request, "dashboard/supervisor.html", context)
