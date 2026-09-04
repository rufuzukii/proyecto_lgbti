#!/usr/bin/env bash
set -euo pipefail

python -m pip install --upgrade pip==26.2.1 setuptools==83.0.0
python -m pip install -e .

venv_root="${VENV_ROOT:-$(python -c 'import sys; print(sys.prefix)')}"
browser_root="${venv_root}/kaleido-chrome"
export BROWSER_PATH="${browser_root}/chrome-linux64/chrome"

mkdir -p "${browser_root}"

printf 'chart_export_build browser_root=%s\n' "${browser_root}"
plotly_get_chrome -y --path "${browser_root}"
test -x "${BROWSER_PATH}"
python scripts/check_chart_export.py
