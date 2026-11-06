from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView

from accounts.views import home

admin.site.site_header = "Service Hours administration"

urlpatterns = [
    path("", home, name="home"),
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("", include("hours.urls")),
    path("teacher/", include("dashboard.urls")),
    path(
        "manifest.webmanifest",
        TemplateView.as_view(
            template_name="manifest.webmanifest", content_type="application/manifest+json"
        ),
        name="manifest",
    ),
]
