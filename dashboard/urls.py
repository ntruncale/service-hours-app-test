from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.roster, name="roster"),
    path("students/<int:pk>/", views.student_detail, name="student"),
    path("entries/<int:pk>/review/", views.entry_review, name="entry_review"),
    path("entries/<int:pk>/resend/", views.entry_resend, name="entry_resend"),
    path("waiting/", views.waiting, name="waiting"),
    path("flagged/", views.flagged, name="flagged"),
    path("summary/", views.summary, name="summary"),
    path("organizations/", views.organizations, name="organizations"),
    path("supervisor/", views.supervisor_lookup, name="supervisor"),
]
