#!/usr/bin/env bash
set -euo pipefail

venv_root="${VENV_ROOT:-$(python -c 'import sys; print(sys.prefix)')}"
export BROWSER_PATH="${venv_root}/kaleido-chrome/chrome-linux64/chrome"

printf 'chart_export_runtime_preflight user=%s browser_path=%s\n' "$(id -un)" "${BROWSER_PATH}"
python scripts/check_chart_export.py --single-only

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
