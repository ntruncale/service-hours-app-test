import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import microsoft
from .forms import OnboardingForm
from .models import User

log = logging.getLogger(__name__)
BACKEND = "django.contrib.auth.backends.ModelBackend"


@login_required
def home(request):
    if request.user.is_student:
        return redirect("hours:my_hours")
    if request.user.is_teacher or request.user.is_school_admin:
        return redirect("dashboard:roster")
    raise Http404


def login_page(request):
    if request.user.is_authenticated:
        return redirect("home")
    return render(request, "accounts/login.html")


def microsoft_login(request):
    redirect_uri = request.build_absolute_uri(settings.MS_REDIRECT_PATH)
    try:
        flow = microsoft.start_flow(redirect_uri)
    except RuntimeError as exc:
        messages.error(request, str(exc))
        return redirect("accounts:login")
    request.session["ms_auth_flow"] = flow
    return redirect(flow["auth_uri"])


def microsoft_callback(request):
    flow = request.session.pop("ms_auth_flow", None)
    if not flow:
        messages.error(request, "Your sign-in session expired. Please try again.")
        return redirect("accounts:login")
    try:
        result = microsoft.finish_flow(flow, request.GET.dict())
    except ValueError:  # state mismatch or replayed callback
        log.warning("Rejected Microsoft callback with bad state")
        messages.error(request, "Sign-in could not be verified. Please try again.")
        return redirect("accounts:login")

    if "error" in result:
        log.warning("Microsoft sign-in error: %s", result.get("error_description"))
        messages.error(request, "Microsoft sign-in failed. Please try again.")
        return redirect("accounts:login")

    claims = result.get("id_token_claims", {})
    if claims.get("tid") != settings.MS_TENANT_ID:
        messages.error(request, "Please sign in with your school Microsoft account.")
        return redirect("accounts:login")

    user = user_from_claims(claims)
    if not user.is_active:
        messages.error(request, "Your account is disabled. Contact your teacher.")
        return redirect("accounts:login")
    login(request, user, backend=BACKEND)
    return redirect("home")


def user_from_claims(claims: dict) -> User:
    """Find or create the local user for a Microsoft identity, and keep roles in sync."""
    oid = claims["oid"]
    email = (claims.get("preferred_username") or claims.get("email") or "").lower()
    name = claims.get("name", "")
    first, _, last = name.partition(" ")

    user = User.objects.filter(ms_oid=oid).first()
    if user is None:
        # A teacher or admin may have been created in the admin site before first sign-in.
        user = User.objects.filter(email__iexact=email, ms_oid__isnull=True).first()
    if user is None:
        user = User(username=email or oid, ms_oid=oid)

    user.ms_oid = oid
    user.email = email
    user.first_name = user.first_name or first
    user.last_name = user.last_name or last

    if email in settings.ADMIN_EMAILS:
        user.role = User.Role.ADMIN
    elif email in settings.TEACHER_EMAILS:
        user.role = User.Role.TEACHER
    user.is_staff = user.is_superuser = user.role == User.Role.ADMIN
    user.set_unusable_password()
    user.save()
    return user


def dev_login(request):
    """Local testing only: sign in as any user without Microsoft."""
    if not settings.DEV_LOGIN_ENABLED:
        raise Http404
    if request.method == "POST":
        user = get_object_or_404(User, pk=request.POST.get("user_id"), is_active=True)
        login(request, user, backend=BACKEND)
        return redirect("home")
    users = User.objects.order_by("role", "graduation_year", "last_name")
    return render(request, "accounts/dev_login.html", {"users": users})


@require_POST
def logout_view(request):
    logout(request)
    messages.info(request, "You are signed out.")
    return redirect("accounts:login")


@login_required
def onboarding(request):
    if not request.user.is_student or request.user.graduation_year:
        return redirect("home")
    form = OnboardingForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        request.user.graduation_year = form.cleaned_data["graduation_year"]
        request.user.save(update_fields=["graduation_year"])
        return redirect("home")
    return render(request, "accounts/onboarding.html", {"form": form})
