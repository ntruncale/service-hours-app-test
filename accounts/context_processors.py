from django.conf import settings


def school(request):
    return {"SCHOOL_NAME": settings.SCHOOL_NAME, "DEV_LOGIN_ENABLED": settings.DEV_LOGIN_ENABLED}
