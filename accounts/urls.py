from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.login_page, name="login"),
    path("microsoft/", views.microsoft_login, name="microsoft_login"),
    path("microsoft/callback/", views.microsoft_callback, name="microsoft_callback"),
    path("dev-login/", views.dev_login, name="dev_login"),
    path("logout/", views.logout_view, name="logout"),
    path("welcome/", views.onboarding, name="onboarding"),
]
