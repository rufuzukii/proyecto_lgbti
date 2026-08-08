from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import fitz
import plotly.graph_objects as go
from dash import Dash
from PIL import Image

from app.analytics.statistics_exports import (
    _prepare_report_figure,
    export_figure_for_report,
)
from app.auth.permissions import Permission, user_has_permission
from app.dash.pages import reports as reports_page
from app.dash_app import _report_params
from app.reports import service as report_service
from app.reports.builder import HRReportBuilder
from app.reports.models import (
    ReportConfiguration,
    ReportDataset,
    sanitize_report_text,
)
from app.reports.pdf_exporter import PDFExporter
from app.users.schemas import UserRole, UserType


def _fra_result() -> dict[str, Any]:
    detail = [
        {"country": "España", "iso": "ES", "answer": "Yes", "percentage": 64.0},
        {"country": "España", "iso": "ES", "answer": "No", "percentage": 36.0},
        {"country": "Francia", "iso": "FR", "answer": "Yes", "percentage": 55.0},
        {"country": "Francia", "iso": "FR", "answer": "No", "percentage": 45.0},
        {"country": "Alemania", "iso": "DE", "answer": "Yes", "percentage": 49.0},
        {"country": "Alemania", "iso": "DE", "answer": "No", "percentage": 51.0},
    ]
    return {
        "status": "ok",
        "source": "FRA",
        "year": 2024,
        "category": "Employment",
        "indicator": "Workplace discrimination",
        "indicator_code": "EMP_1",
        "answer": "Yes",
        "ranking": [
            {"country": "España", "iso": "ES", "value": 64.0},
            {"country": "Francia", "iso": "FR", "value": 55.0},
            {"country": "Alemania", "iso": "DE", "value": 49.0},
            {"country": "Portugal", "iso": "PT", "value": None},
        ],
        "detail_data": detail,
        "data": [row for row in detail if row["answer"] == "Yes"],
        "methodology": "Aggregated FRA survey data.",
    }


def _configuration(**overrides: Any) -> ReportConfiguration:
    values = {
        "source": "fra",
        "category": "Employment",
        "indicator_id": "EMP_1",
        "answer": "Yes",
        "year": 2024,
        "countries": ["ES", "FR"],
        "primary_country": "ES",
        "language": "es",
        "mode": "automatic",
        **overrides,
    }
    return ReportConfiguration.from_mapping(values)


def _ilga_result() -> dict[str, Any]:
    return {
        "status": "ok",
        "source": "ILGA-Europe",
        "year": 2026,
        "category": "Ranking total",
        "indicator": "Ranking total",
        "ranking": [
            {"country": "España", "iso": "ES", "value": 78.0},
            {"country": "Francia", "iso": "FR", "value": 69.0},
            {"country": "Alemania", "iso": "DE", "value": 61.0},
        ],
        "data": [],
        "history": [
            {"country": "España", "iso": "ES", "year": 2024, "value": 74.0},
            {"country": "España", "iso": "ES", "year": 2025, "value": 76.0},
            {"country": "España", "iso": "ES", "year": 2026, "value": 78.0},
            {"country": "Francia", "iso": "FR", "year": 2024, "value": 66.0},
            {"country": "Francia", "iso": "FR", "year": 2026, "value": 69.0},
        ],
    }


def test_report_configuration_sanitizes_user_text_and_keeps_only_identifiers() -> None:
    config = ReportConfiguration.from_mapping(
        {
            "title": "<script>alert(1)</script> Informe",
            "organization": "<b>Empresa</b>",
            "countries": ["es", "../FR", "ES", "DE"],
            "primary_country": "es",
            "mode": "custom",
            "sections": ["metrics", "sources", "unknown"],
            "charts": ["ranking", "invalid"],
            "year": "2024",
        }
    )

    assert config.title == "alert(1) Informe"
    assert config.organization == "Empresa"
    assert config.countries == ("ES", "DE")
    assert config.primary_country == "ES"
    assert config.sections == ("metrics", "sources")
    assert config.charts == ("ranking",)
    assert config.year == 2024
    assert sanitize_report_text("\x00hola") == "hola"


def test_automatic_mode_uses_professional_default_content() -> None:
    config = ReportConfiguration.from_mapping(
        {
            "mode": "automatic",
            "sections": [],
            "charts": [],
        }
    )

    assert "recommendations" in config.sections
    assert "ranking" in config.charts
    assert len(config.charts) <= 8


def test_builder_calculates_metrics_rules_and_reuses_shared_plotly_figures() -> None:
    content = HRReportBuilder().build(
        _configuration(),
        ReportDataset(_fra_result(), query_seconds=0.015),
    )

    metrics = {metric.key: metric for metric in content.metrics}
    assert metrics["eu_average"].numeric_value == 56.0
    assert metrics["country_value"].numeric_value == 64.0
    assert metrics["difference"].numeric_value == 8.0
    assert metrics["relative_difference"].numeric_value == 14.285714285714285
    assert metrics["rank"].display_value == "1/3"
    assert any(item.derived_from_metrics for item in content.recommendations)
    assert 4 <= len(content.charts) <= 8
    assert all(isinstance(chart.figure, go.Figure) for chart in content.charts)
    assert content.table_rows[0]["country"] == "España"
    assert "puntos porcentuales" in content.executive_summary[0]
    assert content.workplace_analysis
    assert content.demographic_analysis == []


def test_builder_supports_ilga_and_english_temporal_report() -> None:
    config = ReportConfiguration.from_mapping(
        {
            "source": "ilga",
            "category": "Ranking total",
            "year": 2026,
            "countries": ["ES", "FR"],
            "primary_country": "ES",
            "language": "en",
            "mode": "automatic",
        }
    )

    content = HRReportBuilder().build(
        config,
        ReportDataset(_ilga_result(), query_seconds=0.01),
    )

    assert content.source_name == "ILGA-Europe"
    assert "percentage points" in content.executive_summary[0]
    assert any(chart.key == "temporal" for chart in content.charts)
    assert all("FRA" not in source for source in content.sources)
    assert all(not item.derived_from_metrics for item in content.recommendations)


def test_builder_handles_europe_scope_and_selected_country_without_data() -> None:
    europe = HRReportBuilder().build(
        _configuration(countries=[], primary_country=""),
        ReportDataset(_fra_result(), query_seconds=0.01),
    )
    missing = HRReportBuilder().build(
        _configuration(countries=["PT"], primary_country="PT"),
        ReportDataset(_fra_result(), query_seconds=0.01),
    )

    assert "country_value" not in {metric.key for metric in europe.metrics}
    assert len(europe.table_rows) == 3
    assert "country_value" not in {metric.key for metric in missing.metrics}
    assert missing.table_rows == []
    assert any("exclu" in item for item in missing.limitations)


def test_custom_mode_hides_disabled_sections_and_adds_active_segmentation() -> None:
    config = _configuration(
        mode="custom",
        sections=["metrics", "demographics"],
        charts=["ranking"],
        filter_a_name="Age",
        filter_a_value="25-39",
    )
    content = HRReportBuilder().build(
        config,
        ReportDataset(_fra_result(), query_seconds=0.01),
    )

    preview = reports_page._preview_content(content)
    rendered_text = " ".join(_collect_text(preview))

    assert content.demographic_analysis
    assert "25-39" in rendered_text
    assert "Fuentes" in rendered_text
    assert "Recomendaciones" not in rendered_text
    assert len(content.charts) == 1


def test_report_dataset_uses_one_query_for_all_countries(monkeypatch) -> None:
    calls = []

    def fake_query(query):
        calls.append(query)
        return _fra_result()

    monkeypatch.setattr(report_service, "get_fra_statistics", fake_query)

    dataset = report_service.load_report_dataset(_configuration())

    assert dataset.result["status"] == "ok"
    assert len(calls) == 1
    assert calls[0].countries == []
    assert calls[0].question_code == "EMP_1"
    assert calls[0].answer == "Yes"


def test_server_png_export_is_valid_and_document_resolution() -> None:
    image_bytes = export_figure_for_report(
        go.Figure(go.Bar(x=["España", "Francia"], y=[64, 55])),
        width=800,
        height=450,
        scale=1,
    )
    image_path = Path("tmp/pdfs/test-report-chart.png")
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(image_bytes)
    try:
        with Image.open(image_path) as image:
            assert image.format == "PNG"
            assert image.size == (800, 450)
    finally:
        image_path.unlink(missing_ok=True)


def test_report_export_removes_interactive_selection_annotations() -> None:
    figure = go.Figure(go.Bar(x=[64], y=["España"], orientation="h"))
    figure.add_annotation(text="Seleccionado", x=1, y="España")

    prepared = _prepare_report_figure(figure)

    assert [annotation.text for annotation in figure.layout.annotations] == ["Seleccionado"]
    assert list(prepared.layout.annotations) == []


def test_pdf_export_contains_sections_charts_and_page_numbers(tmp_path: Path) -> None:
    content = HRReportBuilder().build(
        _configuration(
            mode="custom",
            charts=["ranking", "average"],
            sections=[
                "executive",
                "methodology",
                "metrics",
                "comparison",
                "risks",
                "recommendations",
                "limitations",
                "sources",
            ],
        ),
        ReportDataset(_fra_result(), query_seconds=0.01),
    )
    chart_paths = {}
    for chart in content.charts:
        path = tmp_path / f"{chart.key}.png"
        path.write_bytes(
            export_figure_for_report(
                chart.figure,
                width=1000,
                height=560,
                scale=1,
            )
        )
        chart_paths[chart.key] = path

    pdf_bytes = PDFExporter().export(content, chart_paths)
    document = fitz.open(stream=pdf_bytes, filetype="pdf")
    extracted = "\n".join(cast(str, page.get_text()) for page in document)

    assert pdf_bytes.startswith(b"%PDF")
    assert len(document) >= 3
    assert "Informe de diversidad" in extracted
    assert "Resumen ejecutivo" in extracted
    assert "Recomendaciones para RRHH" in extracted
    assert "EU LGBTIQ Survey III, 2023" in extracted
    assert "España" in extracted
    assert "RainbowLens Datahub" in extracted
    metadata = document.metadata
    assert metadata is not None
    assert metadata["creator"] == "RainbowLens Datahub"
    assert metadata["producer"] == "RainbowLens Datahub"
    assert "ReportLab" not in " ".join(str(value) for value in metadata.values())


def test_generate_report_cleans_temporary_directory(monkeypatch) -> None:
    content = HRReportBuilder().build(
        _configuration(charts=["ranking"]),
        ReportDataset(_fra_result(), query_seconds=0.01),
    )
    observed_roots: list[Path] = []

    monkeypatch.setattr(report_service, "build_report", lambda _config: content)

    def fake_export(_figures, paths):
        for path_value in paths:
            path = Path(path_value)
            observed_roots.append(path.parent)
            path.write_bytes(b"png")
        return [Path(path) for path in paths]

    monkeypatch.setattr(report_service, "export_figures_for_report", fake_export)
    monkeypatch.setattr(
        report_service.PDFExporter,
        "export",
        lambda _self, _content, _images: b"%PDF-test",
    )

    generated = report_service.generate_report_pdf(_configuration())

    assert generated.pdf_bytes == b"%PDF-test"
    assert generated.filename.endswith(".pdf")
    assert observed_roots
    assert all(not root.exists() for root in observed_roots)

    second = report_service.generate_report_pdf(_configuration())
    assert second.pdf_bytes == b"%PDF-test"
    assert all(not root.exists() for root in observed_roots)


def test_report_permissions_are_server_side() -> None:
    assert user_has_permission(
        SimpleNamespace(is_authenticated=True, role=UserRole.ADMIN),
        Permission.GENERATE_REPORTS,
    )
    assert user_has_permission(
        SimpleNamespace(is_authenticated=True, role=UserRole.COMMON),
        Permission.GENERATE_REPORTS,
    )
    assert not user_has_permission(
        SimpleNamespace(is_authenticated=False, role=UserRole.ANONYMOUS),
        Permission.GENERATE_REPORTS,
    )


def test_advanced_report_configuration_is_profile_and_server_protected(monkeypatch) -> None:
    custom = {
        **_configuration().to_dict(),
        "mode": "custom",
        "detail_level": "detailed",
        "sections": ["executive"],
        "charts": ["ranking"],
    }
    monkeypatch.setattr(
        reports_page,
        "current_user",
        SimpleNamespace(
            is_authenticated=True,
            role=UserRole.COMMON,
            user_type=UserType.COMUN,
        ),
    )
    basic = reports_page._report_configuration_for_user(custom)
    assert basic.mode == "automatic"
    assert basic.detail_level == "standard"

    for profile in (UserType.RRHH, UserType.POLITICO, UserType.ONG):
        monkeypatch.setattr(
            reports_page,
            "current_user",
            SimpleNamespace(
                is_authenticated=True,
                role=UserRole.COMMON,
                user_type=profile,
            ),
        )
        advanced = reports_page._report_configuration_for_user(custom)
        assert advanced.mode == "custom"
        assert advanced.detail_level == "detailed"
        assert advanced.sections == ("executive",)


def test_advanced_content_controls_are_disabled_for_common_profile() -> None:
    panel = reports_page._content_panel(_configuration(), advanced_enabled=False)
    toggle = _component_by_id(panel, "report-advanced-toggle")
    content = _component_by_id(panel, "report-advanced-content")

    assert toggle.disabled is True
    assert "is-collapsed" in content.className
    assert content.to_plotly_json()["props"]["aria-hidden"] == "true"
    for identifier in (
        "report-mode-select",
        "report-detail-select",
        "report-sections-select",
        "report-charts-select",
    ):
        control = _component_by_id(panel, identifier)
        assert all(option["disabled"] is True for option in control.options)


def test_authorized_profiles_can_open_and_keep_advanced_options_stable(monkeypatch) -> None:
    app = Dash(__name__, suppress_callback_exceptions=True)
    reports_page.register_reports_callbacks(app)
    callback = next(
        item["callback"].__wrapped__
        for item in app.callback_map.values()
        if getattr(item.get("callback"), "__wrapped__", None)
        and item["callback"].__wrapped__.__name__ == "toggle_advanced_options"
    )

    authorized_users = [
        SimpleNamespace(
            is_authenticated=True,
            role=UserRole.COMMON,
            user_type=profile,
        )
        for profile in (UserType.RRHH, UserType.POLITICO, UserType.ONG)
    ]
    authorized_users.append(
        SimpleNamespace(
            is_authenticated=True,
            role=UserRole.ADMIN,
            user_type=None,
        )
    )

    for user in authorized_users:
        monkeypatch.setattr(reports_page, "current_user", user)
        assert callback(1, False) == (
            True,
            "reports-advanced-content",
            "false",
            "true",
        )
        assert callback(2, True) == (
            False,
            "reports-advanced-content is-collapsed",
            "true",
            "false",
        )

    monkeypatch.setattr(
        reports_page,
        "current_user",
        SimpleNamespace(
            is_authenticated=True,
            role=UserRole.COMMON,
            user_type=UserType.COMUN,
        ),
    )
    assert callback(1, False) == (
        False,
        "reports-advanced-content is-collapsed",
        "true",
        "false",
    )


def _component_by_id(component: Any, identifier: str):
    if getattr(component, "id", None) == identifier:
        return component
    children = getattr(component, "children", None)
    values = children if isinstance(children, (list, tuple)) else [children]
    for child in values:
        if hasattr(child, "to_plotly_json"):
            try:
                return _component_by_id(child, identifier)
            except LookupError:
                pass
    raise LookupError(identifier)


def test_reports_layout_contains_accessible_flow_and_lightweight_store(monkeypatch) -> None:
    monkeypatch.setattr(reports_page, "assert_analytics_databases_available", lambda: None)
    monkeypatch.setattr(reports_page, "build_navbar", lambda **_kwargs: "")
    monkeypatch.setattr(
        reports_page,
        "current_user",
        SimpleNamespace(
            is_authenticated=True,
            organization="Example Org",
            username="People Team",
        ),
    )
    monkeypatch.setattr(
        reports_page, "_year_options", lambda _source: [{"label": "2024", "value": 2024}]
    )
    monkeypatch.setattr(
        reports_page,
        "_category_options",
        lambda _source, _year: [{"label": "Employment", "value": "Employment"}],
    )
    monkeypatch.setattr(
        reports_page,
        "_indicator_options",
        lambda *_args: [{"label": "Workplace discrimination", "value": "EMP_1"}],
    )
    monkeypatch.setattr(reports_page, "_criterion_options", lambda *_args: [])

    layout = reports_page.build_reports_layout(_configuration().to_dict())
    components = list(_walk(layout))
    ids = {getattr(component, "id", None) for component in components}
    store = next(
        component
        for component in components
        if getattr(component, "id", None) == "report-config-store"
    )

    assert {
        "report-preview-button",
        "report-download-button",
        "report-preview-content",
        "report-download",
        "report-sections-select",
        "report-charts-select",
        "report-advanced-open-store",
        "report-advanced-toggle",
        "report-advanced-content",
    }.issubset(ids)
    store_data = getattr(store, "data", None)
    assert isinstance(store_data, dict)
    assert "result" not in store_data
    assert "figure" not in store_data


def test_reports_callbacks_register_preview_and_download() -> None:
    app = Dash(__name__, suppress_callback_exceptions=True)
    reports_page.register_reports_callbacks(app)

    keys = "\n".join(app.callback_map)
    assert "report-preview-content.children" in keys
    assert "report-download.data" in keys
    assert "report-config-store.data" in keys


def test_report_route_params_keep_only_lightweight_whitelisted_filters() -> None:
    parsed = _report_params(
        {
            "source": ["fra"],
            "indicator_id": ["EMP_1"],
            "countries": ["ES,FR"],
            "sections": ["metrics,recommendations"],
            "frames": ['[{"large": "payload"}]'],
            "password": ["secret"],
        }
    )

    assert parsed == {
        "source": "fra",
        "indicator_id": "EMP_1",
        "countries": ["ES", "FR"],
        "sections": ["metrics", "recommendations"],
    }


def test_render_dependencies_install_plotly_chrome() -> None:
    root = Path(__file__).resolve().parents[3]
    render_config = (root / "render.yaml").read_text(encoding="utf-8")
    requirements = (root / "requirements.txt").read_text(encoding="utf-8")

    assert "plotly_get_chrome -y" in render_config
    assert "kaleido==1.3.0" in requirements
    assert "reportlab==4.5.1" in requirements
    assert "healthCheckPath: /health" in render_config
    assert "type: keyvalue" in render_config
    assert "key: REDIS_URL" in render_config
    assert "property: connectionString" in render_config


def _walk(component):
    yield component
    children = getattr(component, "children", None)
    if children is None:
        return
    values = children if isinstance(children, (list, tuple)) else [children]
    for child in values:
        if hasattr(child, "to_plotly_json"):
            yield from _walk(child)


def _collect_text(value):
    values = value if isinstance(value, (list, tuple)) else [value]
    for item in values:
        if isinstance(item, str):
            yield item
            continue
        children = getattr(item, "children", None)
        if children is not None:
            yield from _collect_text(children)
