#!/usr/bin/env bash
set -euo pipefail

python -m pip install --upgrade pip==26.2.1 setuptools==83.0.0
python -m pip install -e .

venv_root="${VENV_ROOT:-$(python -c 'import sys; print(sys.prefix)')}"
browser_root="${venv_root}/kaleido-chrome"
export BROWSER_PATH="${browser_root}/chrome-linux64/chrome"

mkdir -p "${browser_root}"

printf 'chart_export_build user=%s venv_root=%s browser_root=%s\n' "$(id -un)" "${venv_root}" "${browser_root}"
command -v plotly_get_chrome
command -v kaleido_get_chrome
plotly_get_chrome --help
kaleido_get_chrome --help

plotly_get_chrome -y --path "${browser_root}"
printf 'chart_export_build managed_browser_version_tag\n'
cat "${browser_root}/version_tag.txt"

printf 'chart_export_build PATH browser candidates\n'
command -v google-chrome || true
command -v google-chrome-stable || true
command -v chromium || true
command -v chromium-browser || true
printf 'chart_export_build managed_browser=%s\n' "${BROWSER_PATH}"

test -f "${BROWSER_PATH}"
test -x "${BROWSER_PATH}"
ls -la "$(dirname "${BROWSER_PATH}")"
stat "${BROWSER_PATH}"
file "${BROWSER_PATH}"
if command -v ldd >/dev/null 2>&1; then
  ldd_output="$(ldd "${BROWSER_PATH}")"
  printf '%s\n' "${ldd_output}"
  if grep -q 'not found' <<<"${ldd_output}"; then
    printf 'chart_export_build browser_not_executable reason=missing_shared_library\n' >&2
    exit 1
  fi
fi

"${BROWSER_PATH}" --version
timeout 30 "${BROWSER_PATH}" \
  --headless \
  --no-sandbox \
  --disable-gpu \
  --disable-dev-shm-usage \
  --dump-dom about:blank >/dev/null

python scripts/check_chart_export.py
