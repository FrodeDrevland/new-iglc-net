#!/bin/sh
# Container start: apply migrations, then serve. Used by Docker Compose and Azure App Service.
set -e
python manage.py migrate --noinput
exec gunicorn config.wsgi:application \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers "${GUNICORN_WORKERS:-3}" \
    --timeout "${GUNICORN_TIMEOUT:-120}" \
    --access-logfile - --error-logfile -
