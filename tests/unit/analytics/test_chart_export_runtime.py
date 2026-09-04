from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest

from app.modules.statistics import chart_export_runtime
from app.modules.statistics.chart_export_runtime import ChartExportBrowser


def test_detect_chart_export_browser_uses_supported_environment_override(
    tmp_path: Path,
) -> None:
    browser_path = tmp_path / "chrome"
    browser_path.write_bytes(b"browser")
    browser_path.chmod(0o755)

    browser = chart_export_runtime.detect_chart_export_browser(
        tmp_path / "unused",
        environment={"BROWSER_PATH": str(browser_path), "PATH": ""},
    )

    assert browser == ChartExportBrowser(
        found=True,
        path=browser_path.resolve(),
        executable=True,
        source="BROWSER_PATH",
    )


def test_detect_chart_export_browser_reports_not_found(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chart_export_runtime, "chromium_based_browsers", {})
    monkeypatch.setattr(
        chart_export_runtime,
        "get_chrome_download_path",
        lambda **_kwargs: tmp_path / "missing-default",
    )
    monkeypatch.setattr(
        chart_export_runtime,
        "get_old_chrome_download_path",
        lambda: tmp_path / "missing-old",
    )

    browser = chart_export_runtime.detect_chart_export_browser(
        tmp_path / "missing-prefix",
        environment={"PATH": ""},
    )

    assert not browser.found
    assert not browser.executable
    assert browser.path is None


def test_detect_chart_export_browser_reports_existing_non_executable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    browser_path = tmp_path / "chrome"
    browser_path.write_bytes(b"browser")
    monkeypatch.setattr(chart_export_runtime.os, "access", lambda *_args: False)

    browser = chart_export_runtime.detect_chart_export_browser(
        tmp_path / "unused",
        environment={"BROWSER_PATH": str(browser_path), "PATH": ""},
    )

    assert browser.found
    assert not browser.executable
    assert browser.path == browser_path.resolve()


def test_configure_chart_export_browser_replaces_stale_path_with_managed_copy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    browser_path = tmp_path / "kaleido-chrome" / "chrome-linux64" / "chrome"
    browser_path.parent.mkdir(parents=True)
    browser_path.write_bytes(b"browser")
    browser_path.chmod(0o755)
    monkeypatch.setenv("BROWSER_PATH", str(tmp_path / "stale"))
    monkeypatch.setenv("PATH", "")

    browser = chart_export_runtime.configure_chart_export_browser(tmp_path)

    assert browser.ready
    assert browser.path == browser_path.resolve()
    assert os.environ["BROWSER_PATH"] == str(browser_path.resolve())


def test_runtime_log_distinguishes_missing_and_ready_browser(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing = ChartExportBrowser(False, None, False, None)
    ready_path = tmp_path / "chrome"
    ready = ChartExportBrowser(True, ready_path, True, "managed_venv")
    monkeypatch.setattr(chart_export_runtime, "configure_chart_export_browser", lambda: missing)

    with caplog.at_level(logging.INFO):
        chart_export_runtime.log_chart_export_runtime()
    assert "browser_not_found chart_export_runtime browser_found=false" in caplog.text

    caplog.clear()
    monkeypatch.setattr(chart_export_runtime, "configure_chart_export_browser", lambda: ready)
    with caplog.at_level(logging.INFO):
        chart_export_runtime.log_chart_export_runtime()
    assert "chart_export_runtime browser_found=true" in caplog.text
    assert "browser_executable=true" in caplog.text
