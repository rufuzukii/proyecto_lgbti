from __future__ import annotations

import importlib.metadata
import platform
import subprocess
import sys
from pathlib import Path

import plotly.graph_objects as go
import plotly.io as pio

from app.modules.statistics.chart_export_runtime import configure_chart_export_browser

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def main() -> int:
    _print_versions()
    browser = configure_chart_export_browser()
    print("Browser:")
    print("FOUND" if browser.found else "NOT FOUND")
    print(f"browser_path={browser.path or ''}")
    print(f"browser_executable={str(browser.executable).lower()}")
    print(f"browser_source={browser.source or ''}")
    if not browser.ready or browser.path is None:
        print("Browser --version:")
        print("FAIL")
        print("Kaleido:")
        print("FAIL")
        print("PNG:")
        print("FAIL")
        return 1

    browser_version_ok = _print_browser_version(browser.path)
    minimal_ok = False
    figure = go.Figure(go.Bar(x=["A", "B"], y=[1, 2]))
    try:
        png_bytes = pio.to_image(
            figure,
            format="png",
            width=640,
            height=360,
            scale=1,
            validate=True,
        )
        minimal_ok = _valid_png(png_bytes)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        print(f"kaleido_error={type(exc).__name__}")

    print("Browser --version:")
    print("PASS" if browser_version_ok else "FAIL")
    print("Kaleido:")
    print("PASS" if minimal_ok else "FAIL")
    print("PNG:")
    print("PASS" if minimal_ok else "FAIL")
    return 0 if browser_version_ok and minimal_ok else 1


def _print_versions() -> None:
    print(f"Python: {sys.version.split()[0]}")
    for package in ("plotly", "kaleido", "choreographer"):
        print(f"{package.capitalize()}: {importlib.metadata.version(package)}")


def _print_browser_version(path: Path) -> bool:
    command = [str(path), "--version"]
    if platform.system() == "Windows":
        version_text = _managed_browser_version(path)
        print(f"browser_version={version_text}")
        return bool(version_text)
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"browser_version_error={type(exc).__name__}")
        return False
    version = (completed.stdout or completed.stderr).strip().splitlines()
    version_text = version[0] if version else _managed_browser_version(path)
    print(f"browser_version={version_text}")
    return completed.returncode == 0 and bool(version_text)


def _managed_browser_version(path: Path) -> str:
    version_tag = path.parent.parent / "version_tag.txt"
    try:
        return version_tag.read_text(encoding="utf-8").splitlines()[0].strip()
    except (IndexError, OSError):
        return ""


def _valid_png(value: bytes) -> bool:
    return len(value) > len(PNG_SIGNATURE) and value.startswith(PNG_SIGNATURE)


if __name__ == "__main__":
    raise SystemExit(main())
