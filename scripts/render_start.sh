#!/usr/bin/env bash
set -euo pipefail

exec gunicorn wsgi:server \
  --bind "0.0.0.0:${PORT}" \
  --worker-class gthread \
  --workers "${WEB_CONCURRENCY:-1}" \
  --threads "${GUNICORN_THREADS:-4}" \
  --timeout "${GUNICORN_TIMEOUT:-180}" \
  --keep-alive 5 \
  --max-requests 1000 \
  --max-requests-jitter 100 \
  --access-logfile - \
  --error-logfile -
