from django.contrib import messages
from django.core.cache import cache
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts import school_year
from accounts.decorators import student_required

from . import services
from .forms import ServiceEntryForm, SupervisorDecisionForm
from .models import ApprovalRequest, ServiceEntry


def client_ip(request) -> str | None:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    return forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")


# --- Student pages --------------------------------------------------------------


@student_required
def my_hours(request):
    entries = request.user.entries.prefetch_related("approval_requests")
    years = {}
    for entry in entries:
        years.setdefault(entry.school_year, []).append(entry)
    context = {
        "progress": services.progress_for(request.user),
        "years": [
            (school_year.school_year_label(y), items)
            for y, items in sorted(years.items(), reverse=True)
        ],
        "grade": request.user.current_grade,
    }
    return render(request, "hours/my_hours.html", context)


@student_required
def entry_form(request, pk=None):
    entry = None
    if pk:
        entry = get_object_or_404(ServiceEntry, pk=pk, student=request.user)
        if not entry.is_editable:
            messages.error(request, "Approved entries can't be changed. Ask your teacher.")
            return redirect("hours:my_hours")
    instance = entry or ServiceEntry(student=request.user)
    form = ServiceEntryForm(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        services.submit_entry(form.save(commit=False), actor=request.user)
        messages.success(
            request, f"Saved. We emailed {form.instance.supervisor_email} to confirm your hours."
        )
        return redirect("hours:my_hours")
    return render(request, "hours/entry_form.html", {"form": form, "entry": entry})


@student_required
@require_POST
def entry_delete(request, pk):
    entry = get_object_or_404(ServiceEntry, pk=pk, student=request.user)
    if entry.counts:
        messages.error(request, "Approved entries can't be deleted. Ask your teacher.")
    else:
        services.audit(None, "entry deleted", actor=request.user, detail=str(entry))
        entry.delete()
        messages.success(request, "Entry deleted.")
    return redirect("hours:my_hours")


@student_required
@require_POST
def entry_resend(request, pk):
    entry = get_object_or_404(ServiceEntry, pk=pk, student=request.user)
    if services.can_resend(entry):
        services.resend(entry, actor=request.user)
        messages.success(request, f"We sent a new link to {entry.supervisor_email}.")
    else:
        messages.error(
            request, "You can resend once an hour for entries that are waiting or expired."
        )
    return redirect("hours:my_hours")


# --- Supervisor approval (no login) -----------------------------------------------

RATE_LIMIT = 30  # requests per IP per 10 minutes


def _rate_limited(request) -> bool:
    key = f"approve-rl:{client_ip(request)}"
    cache.add(key, 0, timeout=600)
    return cache.incr(key) > RATE_LIMIT


def approve(request, token):
    if _rate_limited(request):
        return HttpResponse("Too many requests. Please try again later.", status=429)

    req = ApprovalRequest.find(token)
    if req is None:
        return render(request, "hours/approve_invalid.html", {"reason": "invalid"}, status=404)
    if not req.is_usable:
        reason = "answered" if req.responded_at else ("expired" if req.is_expired else "replaced")
        return render(
            request, "hours/approve_invalid.html", {"reason": reason, "req": req}, status=410
        )

    # Opening the page (GET) never changes the decision. Email scanners open links
    # automatically; only a person pressing a button (POST) can approve.
    form = SupervisorDecisionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        approve_it = form.cleaned_data["decision"] == "approve"
        try:
            services.record_supervisor_decision(
                req,
                approve=approve_it,
                typed_name=form.cleaned_data["typed_name"],
                comment=form.cleaned_data["comment"],
                ip=client_ip(request),
            )
        except ValueError:
            return render(request, "hours/approve_invalid.html", {"reason": "answered"}, status=410)
        return render(
            request, "hours/approve_done.html", {"approved": approve_it, "entry": req.entry}
        )

    if request.method == "GET" and req.opened_at is None:
        req.opened_at = timezone.now()
        req.save(update_fields=["opened_at"])
    return render(request, "hours/approve.html", {"req": req, "entry": req.entry, "form": form})
