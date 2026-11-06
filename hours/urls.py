from django.urls import path

from . import views

app_name = "hours"

urlpatterns = [
    path("my-hours/", views.my_hours, name="my_hours"),
    path("my-hours/new/", views.entry_form, name="entry_new"),
    path("my-hours/<int:pk>/edit/", views.entry_form, name="entry_edit"),
    path("my-hours/<int:pk>/delete/", views.entry_delete, name="entry_delete"),
    path("my-hours/<int:pk>/resend/", views.entry_resend, name="entry_resend"),
    path("approve/<str:token>/", views.approve, name="approve"),
]
