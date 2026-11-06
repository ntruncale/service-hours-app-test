#!/usr/bin/env bash
# Production start command (Azure App Service, Render, Railway...).
set -euo pipefail
python manage.py migrate --noinput
python manage.py collectstatic --noinput
exec gunicorn config.wsgi --bind "0.0.0.0:${PORT:-8000}" --workers "${WEB_CONCURRENCY:-3}" --timeout 60
