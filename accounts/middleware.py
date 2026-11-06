from django.shortcuts import redirect
from django.urls import reverse


class OnboardingMiddleware:
    """Students must tell us their graduation year before using the app."""

    ALLOWED_PREFIXES = ("/accounts/", "/static/", "/approve/", "/admin/", "/manifest")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if (
            user.is_authenticated
            and user.is_student
            and user.graduation_year is None
            and not request.path.startswith(self.ALLOWED_PREFIXES)
        ):
            return redirect(reverse("accounts:onboarding"))
        return self.get_response(request)
