from __future__ import annotations

import argparse
import importlib.metadata
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

import plotly.graph_objects as go
import plotly.io as pio

from app.modules.statistics.chart_export_runtime import configure_chart_export_browser
from app.modules.statistics.exports import export_figures_for_report

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify the browser and Plotly/Kaleido static chart export stack."
    )
    parser.add_argument(
        "--single-only",
        action="store_true",
        help="Only run the minimal one-figure export used before Gunicorn starts.",
    )
    arguments = parser.parse_args()

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
    batch_ok = False
    helper_ok = False
    with tempfile.TemporaryDirectory(prefix="rainbowlens-chart-export-check-") as temp_dir:
        root = Path(temp_dir)
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
            minimal_path = root / "minimal.png"
            minimal_path.write_bytes(png_bytes)
            minimal_ok = _valid_png(minimal_path)
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            print(f"minimal_error={type(exc).__name__}")

        if not arguments.single_only and minimal_ok:
            direct_paths = [root / "batch-1.png", root / "batch-2.png"]
            try:
                pio.write_images(
                    [figure, figure],
                    [str(path) for path in direct_paths],
                    format="png",
                    width=640,
                    height=360,
                    scale=1,
                    validate=True,
                )
                batch_ok = all(_valid_png(path) for path in direct_paths)
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                print(f"batch_error={type(exc).__name__}")

            helper_paths = [root / f"helper-{index}.png" for index in range(1, 6)]
            try:
                rendered = export_figures_for_report(
                    [figure for _path in helper_paths],
                    helper_paths,
                    width=640,
                    height=360,
                    scale=1,
                )
                helper_ok = len(rendered) == 5 and all(_valid_png(path) for path in rendered)
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                print(f"rainbowlens_error={type(exc).__name__}")

    print("Browser --version:")
    print("PASS" if browser_version_ok else "FAIL")
    print("Kaleido:")
    print("PASS" if minimal_ok else "FAIL")
    print("PNG:")
    print("PASS" if minimal_ok else "FAIL")
    if not arguments.single_only:
        print("pio.write_images:")
        print("PASS" if batch_ok else "FAIL")
        print("export_figures_for_report:")
        print("PASS" if helper_ok else "FAIL")
    required_checks = [browser_version_ok, minimal_ok]
    if not arguments.single_only:
        required_checks.extend((batch_ok, helper_ok))
    return 0 if all(required_checks) else 1


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


def _valid_png(path: Path) -> bool:
    try:
        return path.stat().st_size > len(PNG_SIGNATURE) and path.read_bytes().startswith(
            PNG_SIGNATURE
        )
    except OSError:
        return False


if __name__ == "__main__":
    raise SystemExit(main())
