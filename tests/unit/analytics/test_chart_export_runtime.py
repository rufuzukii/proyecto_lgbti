from __future__ import annotations

import logging
import os
from pathlib import Path

import plotly.graph_objects as go
import pytest

from app.modules.statistics import chart_export_runtime, exports
from app.modules.statistics.chart_export_runtime import ChartExportBrowser

PNG = b"\x89PNG\r\n\x1a\nvalid"


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


def test_export_stops_before_kaleido_when_browser_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        exports,
        "configure_chart_export_browser",
        lambda: ChartExportBrowser(False, None, False, None),
    )
    monkeypatch.setattr(
        exports.pio,
        "to_image",
        lambda *_args, **_kwargs: pytest.fail("Kaleido must not run without a browser"),
    )

    with pytest.raises(exports.ChartExportError):
        exports.export_figure_for_report(go.Figure(go.Bar(x=["A"], y=[1])))


def test_export_logs_kaleido_initialization_failure(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    browser = ChartExportBrowser(True, tmp_path / "chrome", True, "test")
    monkeypatch.setattr(exports, "configure_chart_export_browser", lambda: browser)

    class BrowserFailedError(RuntimeError):
        pass

    def fail_export(*_args, **_kwargs):
        raise BrowserFailedError("browser closed during startup")

    monkeypatch.setattr(exports.pio, "to_image", fail_export)

    with caplog.at_level(logging.ERROR), pytest.raises(exports.ChartExportError):
        exports.export_figure_for_report(go.Figure(go.Bar(x=["A"], y=[1])))

    assert "kaleido_initialization_failed" in caplog.text


def test_batch_export_validates_every_png(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    browser = ChartExportBrowser(True, tmp_path / "chrome", True, "test")
    monkeypatch.setattr(exports, "configure_chart_export_browser", lambda: browser)

    def write_figure(_figure, path, **_kwargs):
        Path(path).write_bytes(PNG)
        return ()

    monkeypatch.setattr(exports.kaleido, "write_fig_sync", write_figure)
    paths = [tmp_path / "one.png", tmp_path / "two.png"]

    rendered = exports.export_figures_for_report(
        [go.Figure(), go.Figure()],
        paths,
    )

    assert rendered == paths
    assert all(path.read_bytes() == PNG for path in paths)


def test_large_export_writes_one_figure_per_bounded_browser_lifecycle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    browser = ChartExportBrowser(True, tmp_path / "chrome", True, "test")
    monkeypatch.setattr(exports, "configure_chart_export_browser", lambda: browser)
    writes: list[tuple[Path, dict[str, object]]] = []

    def write_figure(_figure, path, **kwargs):
        target = Path(path)
        writes.append((target, kwargs))
        target.write_bytes(PNG)
        return ()

    monkeypatch.setattr(exports.kaleido, "write_fig_sync", write_figure)
    paths = [tmp_path / f"chart-{index}.png" for index in range(8)]

    rendered = exports.export_figures_for_report(
        [go.Figure() for _index in paths],
        paths,
    )

    assert rendered == paths
    assert [path for path, _kwargs in writes] == paths
    assert all(kwargs["kopts"] == {"n": 1, "timeout": 60} for _path, kwargs in writes)
    assert all(kwargs["cancel_on_error"] is True for _path, kwargs in writes)
    assert all(path.read_bytes() == PNG for path in paths)


def test_report_payload_removes_interactive_only_data() -> None:
    figure = go.Figure(
        go.Bar(
            x=["A"],
            y=[1],
            customdata=[["large hover value"]],
            hovertemplate="%{customdata[0]}",
            meta="interactive metadata",
        )
    )
    figure.update_layout(meta={"export_filename": "chart.png"})

    payload = exports._prepare_report_payload(figure)

    assert payload["data"][0]["x"] == ["A"]
    assert payload["data"][0]["y"] == [1]
    assert payload["data"][0]["hoverinfo"] == "skip"
    assert "customdata" not in payload["data"][0]
    assert "hovertemplate" not in payload["data"][0]
    assert "meta" not in payload["data"][0]
    assert "meta" not in payload["layout"]
    assert getattr(figure.data[0], "customdata", None) is not None


def test_batch_export_rejects_missing_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    browser = ChartExportBrowser(True, tmp_path / "chrome", True, "test")
    monkeypatch.setattr(exports, "configure_chart_export_browser", lambda: browser)
    monkeypatch.setattr(exports.kaleido, "write_fig_sync", lambda *_args, **_kwargs: ())

    with pytest.raises(exports.ChartExportError):
        exports.export_figures_for_report(
            [go.Figure()],
            [tmp_path / "missing.png"],
        )
