#!/bin/sh
# Apply migrations and publish Django admin static files for Caddy, then run the given command.
set -e
python manage.py migrate --noinput
python manage.py collectstatic --noinput --clear >/dev/null
cp -r staticfiles/. /static/ 2>/dev/null || true
exec "$@"
