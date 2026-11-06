"""Django settings for the Service Hours app.

Every secret or school-specific value comes from an environment variable.
Copy .env.example to .env for local development; on the server, set them in the
host's configuration screen. Never commit real values.
"""

import os
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Tiny .env reader so students don't need another dependency."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).lower() in {"1", "true", "yes", "on"}


def env_list(name: str) -> list[str]:
    return [item.strip().lower() for item in os.environ.get(name, "").split(",") if item.strip()]


DEBUG = env_bool("DEBUG", False)
SECRET_KEY = os.environ.get("SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG or os.environ.get("PYTEST_VERSION"):
        SECRET_KEY = "dev-only-insecure-key"
    else:
        raise RuntimeError("Set the SECRET_KEY environment variable.")

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS") or (["localhost", "127.0.0.1"] if DEBUG else [])
CSRF_TRUSTED_ORIGINS = [o for o in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if o]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "accounts",
    "hours",
    "dashboard",
    "notifications",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "accounts.middleware.OnboardingMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "accounts.context_processors.school",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}", conn_max_age=600
    )
}

AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "accounts:login"

LANGUAGE_CODE = "en-us"
TIME_ZONE = os.environ.get("TIME_ZONE", "America/Chicago")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG or os.environ.get("PYTEST_VERSION")
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        )
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# --- Security for production -------------------------------------------------
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
    SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_AGE = 60 * 60 * 12  # 12 hours

# --- School settings ---------------------------------------------------------
SCHOOL_NAME = os.environ.get("SCHOOL_NAME", "Our School")
# Month the school year starts (7 = July). Entries are filed under the school year
# that contains their service date; a school year is named by the year it ends.
SCHOOL_YEAR_START_MONTH = int(os.environ.get("SCHOOL_YEAR_START_MONTH", "7"))
MAX_HOURS_PER_DAY = float(os.environ.get("MAX_HOURS_PER_DAY", "12"))
# Public URL of the site, used to build links in emails.
SITE_URL = os.environ.get("SITE_URL", "http://localhost:8000").rstrip("/")

# Supervisor emails ending in these domains are refused (e.g. the student email domain).
BLOCKED_SUPERVISOR_DOMAINS = env_list("BLOCKED_SUPERVISOR_DOMAINS")

# Role assignment at first sign-in. Roles can also be changed later in the admin site.
TEACHER_EMAILS = env_list("TEACHER_EMAILS")
ADMIN_EMAILS = env_list("ADMIN_EMAILS")

# Approval links
APPROVAL_LINK_DAYS = int(os.environ.get("APPROVAL_LINK_DAYS", "14"))
REMINDER_AFTER_DAYS = [
    int(d) for d in os.environ.get("REMINDER_AFTER_DAYS", "4,9").split(",") if d.strip()
]
STALE_PENDING_DAYS = int(os.environ.get("STALE_PENDING_DAYS", "7"))

# --- Microsoft Entra ID (sign-in) -------------------------------------------
MS_TENANT_ID = os.environ.get("MS_TENANT_ID", "")
MS_CLIENT_ID = os.environ.get("MS_CLIENT_ID", "")
MS_CLIENT_SECRET = os.environ.get("MS_CLIENT_SECRET", "")
MS_REDIRECT_PATH = "/accounts/microsoft/callback/"

# Development sign-in page that lets you pick any user. NEVER enable in production.
DEV_LOGIN_ENABLED = DEBUG and env_bool("DEV_LOGIN_ENABLED", True)

# --- Email ---------------------------------------------------------------------
# EMAIL_PROVIDER=console (prints emails in the terminal) or graph (Microsoft Graph sendMail)
EMAIL_PROVIDER = os.environ.get("EMAIL_PROVIDER", "console")
if EMAIL_PROVIDER == "graph":
    EMAIL_BACKEND = "notifications.graph_backend.GraphEmailBackend"
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "servicehours@example.org")
GRAPH_SENDER_MAILBOX = os.environ.get("GRAPH_SENDER_MAILBOX", DEFAULT_FROM_EMAIL)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO")},
}
