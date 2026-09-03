from __future__ import annotations

import logging
import os
import shutil
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from choreographer.browsers._chrome_constants import chromium_based_browsers
from choreographer.cli._cli_utils import (
    get_chrome_download_path,
    get_old_chrome_download_path,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChartExportBrowser:
    """Safe, non-secret browser state used by startup and deploy diagnostics."""

    found: bool
    path: Path | None
    executable: bool
    source: str | None

    @property
    def ready(self) -> bool:
        return self.found and self.executable


def detect_chart_export_browser(
    prefix: str | Path | None = None,
    *,
    environment: Mapping[str, str] | None = None,
) -> ChartExportBrowser:
    """Locate Chrome using the paths understood by Choreographer 1.3."""
    environ = os.environ if environment is None else environment
    candidates = _browser_candidates(prefix, environ)
    first_existing: tuple[Path, str] | None = None
    first_configured: tuple[Path, str] | None = None

    for candidate, source in candidates:
        if first_configured is None and source == "BROWSER_PATH":
            first_configured = (candidate, source)
        if not candidate.is_file():
            continue
        if first_existing is None:
            first_existing = (candidate, source)
        if os.access(candidate, os.X_OK):
            return ChartExportBrowser(
                found=True,
                path=candidate.resolve(),
                executable=True,
                source=source,
            )

    if first_existing is not None:
        candidate, source = first_existing
        return ChartExportBrowser(
            found=True,
            path=candidate.resolve(),
            executable=False,
            source=source,
        )
    if first_configured is not None:
        candidate, source = first_configured
        return ChartExportBrowser(
            found=False,
            path=candidate,
            executable=False,
            source=source,
        )
    return ChartExportBrowser(found=False, path=None, executable=False, source=None)


def configure_chart_export_browser(
    prefix: str | Path | None = None,
) -> ChartExportBrowser:
    """Set Choreographer's supported browser override when a usable browser exists."""
    browser = detect_chart_export_browser(prefix)
    if browser.ready and browser.path is not None:
        os.environ["BROWSER_PATH"] = str(browser.path)
    return browser


def log_chart_export_runtime() -> ChartExportBrowser:
    """Log browser readiness once during application startup without launching Chrome."""
    browser = configure_chart_export_browser()
    if not browser.found:
        logger.error(
            "browser_not_found chart_export_runtime browser_found=false "
            "browser_executable=false"
        )
    elif not browser.executable:
        logger.error(
            "browser_not_executable chart_export_runtime browser_found=true "
            "browser_path=%s browser_executable=false source=%s",
            browser.path,
            browser.source,
        )
    else:
        logger.info(
            "chart_export_runtime browser_found=true browser_path=%s "
            "browser_executable=true source=%s",
            browser.path,
            browser.source,
        )
    return browser


def _browser_candidates(
    prefix: str | Path | None,
    environment: Mapping[str, str],
) -> list[tuple[Path, str]]:
    candidates: list[tuple[Path, str]] = []
    configured = str(environment.get("BROWSER_PATH") or "").strip()
    if configured:
        candidates.append((Path(configured).expanduser(), "BROWSER_PATH"))

    roots: list[Path] = []
    if prefix is not None:
        roots.append(Path(prefix))
    venv_root = str(environment.get("VENV_ROOT") or "").strip()
    if venv_root:
        roots.append(Path(venv_root))
    roots.append(Path(sys.prefix))
    for root in _unique_paths(roots):
        candidates.extend(
            (candidate, "managed_venv") for candidate in _managed_browser_paths(root)
        )

    downloaded = get_chrome_download_path(mkdir=False)
    if downloaded is not None:
        candidates.append((downloaded, "choreographer_download"))
    old_downloaded = get_old_chrome_download_path()
    if old_downloaded is not None:
        candidates.append((old_downloaded, "choreographer_legacy_download"))

    for browser in chromium_based_browsers.values():
        for name in browser.exe_names:
            if resolved := shutil.which(name, path=environment.get("PATH")):
                candidates.append((Path(resolved), "PATH"))
        candidates.extend((Path(path), "typical_path") for path in browser.typical_paths)
    return _unique_candidates(candidates)


def _managed_browser_paths(root: Path) -> tuple[Path, ...]:
    chrome_root = root / "kaleido-chrome"
    return (
        chrome_root / "chrome-linux64" / "chrome",
        chrome_root / "chrome-win64" / "chrome.exe",
        chrome_root / "chrome-win32" / "chrome.exe",
        chrome_root
        / "chrome-mac-x64"
        / "Google Chrome for Testing.app"
        / "Contents"
        / "MacOS"
        / "Google Chrome for Testing",
        chrome_root
        / "chrome-mac-arm64"
        / "Google Chrome for Testing.app"
        / "Contents"
        / "MacOS"
        / "Google Chrome for Testing",
    )


def _unique_paths(values: list[Path]) -> list[Path]:
    unique: list[Path] = []
    seen: set[str] = set()
    for value in values:
        key = str(value)
        if key in seen:
            continue
        seen.add(key)
        unique.append(value)
    return unique


def _unique_candidates(
    values: list[tuple[Path, str]],
) -> list[tuple[Path, str]]:
    unique: list[tuple[Path, str]] = []
    seen: set[str] = set()
    for path, source in values:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        unique.append((path, source))
    return unique
