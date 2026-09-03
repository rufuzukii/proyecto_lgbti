from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import fitz
import plotly.graph_objects as go
from dash import Dash, dcc
from PIL import Image

from app.core.auth.permissions import Permission, user_has_permission
from app.modules.account.users.schemas import UserRole
from app.modules.reports import page as reports_page
from app.modules.reports import service as report_service
from app.modules.reports.builder import HRReportBuilder
from app.modules.reports.models import (
    ReportConfiguration,
    ReportDataset,
    sanitize_report_text,
)
from app.modules.reports.pdf_exporter import PDFExporter
from app.modules.statistics.exports import (
    _configure_kaleido_browser,
    _prepare_report_figure,
    export_figure_for_report,
)
from app.web.application import _report_params


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


def test_report_fields_associate_labels_without_targeting_composite_containers() -> None:
    text_field = reports_page._field("Título", "Title", dcc.Input(id="report-title-test"))
    group_field = reports_page._field(
        "Formato",
        "Format",
        dcc.RadioItems(id="report-format-test", options=[]),
    )
    dropdown_field = reports_page._field(
        "Indicador social",
        "Social indicator",
        dcc.Dropdown(id="report-indicator-test", options=[]),
        required=True,
        error_id="report-indicator-test-error",
    )
    text_props = text_field.to_plotly_json()["props"]
    text_label_props = text_props["children"][0].to_plotly_json()["props"]
    group_props = group_field.to_plotly_json()["props"]
    group_label = group_props["children"][0]

    assert text_label_props["htmlFor"] == "report-title-test"
    assert group_props["role"] == "group"
    assert group_props["aria-labelledby"] == "report-format-test-label"
    assert group_label.to_plotly_json()["type"] == "Span"
    assert "htmlFor" not in group_label.to_plotly_json()["props"]
    dropdown_props = dropdown_field.to_plotly_json()["props"]
    dropdown_label = dropdown_props["children"][0].to_plotly_json()["props"]
    assert dropdown_props["role"] == "group"
    assert dropdown_props["aria-labelledby"] == "report-indicator-test-label"
    assert dropdown_props["aria-required"] == "true"
    assert "htmlFor" not in dropdown_label


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


def _many_country_result(count: int = 12) -> dict[str, Any]:
    countries = [
        ("ES", "Spain"),
        ("FR", "France"),
        ("DE", "Germany"),
        ("NL", "Netherlands"),
        ("GB", "United Kingdom"),
        ("CZ", "Czechia"),
        ("PT", "Portugal"),
        ("IT", "Italy"),
        ("BE", "Belgium"),
        ("AT", "Austria"),
        ("SE", "Sweden"),
        ("FI", "Finland"),
    ][:count]
    result = _fra_result()
    result["ranking"] = [
        {"iso": code, "country": name, "value": float(100 - index)}
        for index, (code, name) in enumerate(countries)
    ]
    return result


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


def test_empty_content_selection_uses_professional_defaults() -> None:
    config = ReportConfiguration.from_mapping(
        {
            "sections": [],
            "charts": [],
        }
    )

    assert "recommendations" in config.sections
    assert "ranking" in config.charts
    assert len(config.charts) == 4


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


def test_social_and_legal_reports_start_with_the_reused_european_map() -> None:
    social = HRReportBuilder().build(
        _configuration(), ReportDataset(_fra_result(), query_seconds=0.01)
    )
    legal = HRReportBuilder().build(
        ReportConfiguration.from_mapping(
            {"source": "ilga", "year": 2026, "language": "es"}
        ),
        ReportDataset(_ilga_result(), query_seconds=0.01),
    )

    assert social.charts[0].key == "map_fra"
    assert cast(Any, social.charts[0].figure.data[0]).type == "choropleth"
    assert legal.charts[0].key == "map_ilga"
    assert cast(Any, legal.charts[0].figure.data[0]).type == "choropleth"


def test_unselected_ranking_reuses_all_statistics_pages_without_losing_countries() -> None:
    content = HRReportBuilder().build(
        _configuration(countries=[], primary_country="", charts=["ranking"]),
        ReportDataset(_many_country_result(), query_seconds=0.01),
    )
    ranking = next(chart for chart in content.charts if chart.key == "ranking")
    page_countries = [
        str(country)
        for figure in ranking.figures
        for country in cast(Any, figure.data[0]).y
    ]

    assert len(ranking.figures) == 3
    assert ranking.page_ranges == [(1, 5), (6, 10), (11, 12)]
    assert [len(cast(Any, figure.data[0]).y) for figure in ranking.figures] == [5, 5, 2]
    assert len(page_countries) == len(set(page_countries)) == 12
    assert len(content.table_rows) == 12


def test_other_multi_country_figures_reuse_the_same_static_page_groups() -> None:
    result = _many_country_result()
    result["detail_data"] = [
        {
            "country": row["country"],
            "iso": row["iso"],
            "answer": answer,
            "percentage": row["value"] if answer == "Yes" else 100 - row["value"],
        }
        for row in result["ranking"]
        for answer in ("Yes", "No")
    ]
    content = HRReportBuilder().build(
        _configuration(
            countries=[],
            primary_country="",
            charts=["countries", "responses"],
        ),
        ReportDataset(result, query_seconds=0.01),
    )

    figures = {chart.key: chart for chart in content.charts}
    assert len(figures["countries"].figures) == 3
    assert len(figures["responses"].figures) == 3
    assert figures["countries"].page_ranges == [(1, 5), (6, 10), (11, 12)]
    response_page_countries = [
        {
            str(country)
            for trace in figure.data
            for country in (getattr(trace, "y", None) or [])
        }
        for figure in figures["responses"].figures
    ]
    assert [len(countries) for countries in response_page_countries] == [5, 5, 2]
    assert all(not figure.layout.annotations for figure in figures["responses"].figures)
    assert not (
        response_page_countries[0]
        & response_page_countries[1]
        | response_page_countries[0]
        & response_page_countries[2]
        | response_page_countries[1]
        & response_page_countries[2]
    )


def test_response_details_only_contains_explicitly_selected_countries() -> None:
    result = _many_country_result()
    result["detail_data"] = [
        {
            "country": row["country"],
            "iso": row["iso"],
            "answer": answer,
            "percentage": row["value"] if answer == "Yes" else 100 - row["value"],
        }
        for row in result["ranking"]
        for answer in ("Yes", "No")
    ]
    content = HRReportBuilder().build(
        _configuration(
            countries=["ES", "DE"],
            primary_country="ES",
            charts=["responses"],
        ),
        ReportDataset(result, query_seconds=0.01),
    )

    responses = next(chart for chart in content.charts if chart.key == "responses")
    rendered_countries = {
        str(country)
        for trace in responses.figure.data
        for country in (getattr(trace, "y", None) or [])
    }

    assert len(responses.figures) == 1
    assert rendered_countries == {"España", "Alemania"}
    assert len(responses.figure.layout.annotations) == 2
    assert {
        annotation.text for annotation in responses.figure.layout.annotations
    } == {"Seleccionado"}


def test_selected_ranking_only_contains_explicit_countries() -> None:
    selected = ["ES", "FR", "DE"]
    content = HRReportBuilder().build(
        _configuration(countries=selected, primary_country="ES", charts=["ranking"]),
        ReportDataset(_many_country_result(), query_seconds=0.01),
    )
    ranking = next(chart for chart in content.charts if chart.key == "ranking")
    countries = set(cast(Any, ranking.figure.data[0]).y)

    assert len(ranking.figures) == 1
    assert countries == {"España", "Francia", "Alemania"}
    assert {row["country"] for row in content.table_rows} == countries


def test_ranking_pages_preserve_global_tied_positions() -> None:
    result = _many_country_result(6)
    values = [100.0, 90.0, 80.0, 70.0, 60.0, 60.0]
    for row, value in zip(result["ranking"], values, strict=True):
        row["value"] = value
    content = HRReportBuilder().build(
        _configuration(countries=[], primary_country="", charts=["ranking"]),
        ReportDataset(result, query_seconds=0.01),
    )
    ranking = next(chart for chart in content.charts if chart.key == "ranking")
    positions = [
        str(item[1])
        for figure in ranking.figures
        for item in cast(Any, figure.data[0]).customdata
    ]

    assert sorted(positions) == [
        "1",
        "2",
        "3",
        "4",
        "5",
        "5",
    ]


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

    assert f'"{content.indicator}"' in rendered_text
    assert content.demographic_analysis
    assert "25-39" in rendered_text
    assert "Fuentes" in rendered_text
    assert "Recomendaciones" not in rendered_text
    assert [chart.key for chart in content.charts] == ["map_fra", "ranking"]
    assert content.charts[0].observation == ""

    textareas: list[Any] = [
        cast(Any, item)
        for component in preview
        for item in _walk(component)
        if isinstance(item, dcc.Textarea)
    ]
    chart_textareas = [
        item for item in textareas if item.id["type"] == "report-chart-narrative"
    ]
    section_textareas = [
        item for item in textareas if item.id["type"] == "report-section-narrative"
    ]
    assert len(chart_textareas) == len(content.charts) * 3
    assert {item.id["field"] for item in chart_textareas} == {
        "what_shows",
        "how_to_read",
        "observation",
    }
    assert all(item.maxLength == 2_000 for item in chart_textareas)
    assert all(item.className == "reports-chart-narrative" for item in chart_textareas)
    assert section_textareas == []


def test_preview_exposes_generated_report_prose_as_editable_textareas() -> None:
    content = HRReportBuilder().build(
        _configuration(),
        ReportDataset(_fra_result(), query_seconds=0.01),
    )

    section_textareas = [
        cast(Any, item)
        for component in reports_page._preview_content(content)
        for item in _walk(component)
        if isinstance(item, dcc.Textarea)
        and cast(Any, item).id["type"] == "report-section-narrative"
    ]

    assert {item.id["section"] for item in section_textareas} == {
        "executive",
        "context",
        "recommendations",
    }
    assert all(item.maxLength == 8_000 for item in section_textareas)
    section_values = {item.id["section"]: item.value for item in section_textareas}
    assert section_values["executive"] == "\n\n".join(content.executive_summary)
    assert content.indicator in section_values["context"]
    assert section_values["recommendations"] == "\n".join(
        item.text for item in content.recommendations
    )


def test_preview_starts_with_executive_summary_and_uses_responsive_components() -> None:
    content = HRReportBuilder().build(
        _configuration(),
        ReportDataset(_fra_result(), query_seconds=0.01),
    )

    preview = reports_page._preview_content(content)
    top_level_text = [" ".join(_collect_text(component)) for component in preview]
    executive_index = next(
        index for index, value in enumerate(top_level_text) if "Resumen ejecutivo" in value
    )
    metrics_index = next(
        index
        for index, component in enumerate(preview)
        if getattr(component, "className", None) == "reports-preview-metrics"
    )
    map_index = next(
        index
        for index, component in enumerate(preview)
        if getattr(component, "className", None) == "reports-preview-chart"
    )
    ranking_index = next(
        index
        for index, component in enumerate(preview)
        if getattr(component, "className", None) == "reports-preview-chart"
        and "Ranking comparativo" in " ".join(_collect_text(component))
    )
    components = [item for component in preview for item in _walk(component)]
    graphs = [item for item in components if isinstance(item, dcc.Graph)]
    grids = [item for item in components if item.__class__.__name__ == "AgGrid"]
    table_wrappers = [
        item
        for item in components
        if getattr(item, "className", None) == "reports-preview-table-scroll"
    ]

    assert executive_index < map_index < metrics_index < ranking_index
    assert "Objetivo del informe" not in " ".join(top_level_text)
    assert graphs
    graph_props = [graph.to_plotly_json()["props"] for graph in graphs]
    assert all(props["responsive"] is True for props in graph_props)
    assert all(props["className"] == "reports-preview-graph" for props in graph_props)
    assert table_wrappers
    assert grids
    grid_props = grids[0].to_plotly_json()["props"]
    assert grid_props["style"] == {"width": "100%", "maxWidth": "100%"}
    assert grid_props["defaultColDef"]["wrapText"] is True
    assert grid_props["defaultColDef"]["flex"] == 1


def test_report_preview_styles_contain_overflow_at_the_source() -> None:
    stylesheet = (
        Path(__file__).resolve().parents[3]
        / "src"
        / "app"
        / "web"
        / "assets"
        / "reports.css"
    ).read_text(encoding="utf-8")

    document_rule = stylesheet.split(".reports-preview-document {", 1)[1].split("}", 1)[0]
    section_rule = stylesheet.split(".reports-preview-section,", 1)[1].split("}", 1)[0]
    textarea_rule = stylesheet.split(".reports-chart-narrative,", 1)[1].split("}", 1)[0]
    editor_rule = stylesheet.split(".reports-chart-editor {", 1)[1].split("}", 1)[0]
    field_rule = stylesheet.split(".reports-chart-editor-field {", 1)[1].split("}", 1)[0]
    section_editor_rule = stylesheet.split(".reports-section-editor {", 1)[1].split("}", 1)[0]
    table_rule = stylesheet.split(".reports-preview-table-scroll {", 1)[1].split("}", 1)[0]

    assert "width: 100%;" in document_rule
    assert "max-width: 980px;" in document_rule
    assert "min-width: 0;" in document_rule
    assert "max-width: 100%;" in section_rule
    assert "min-width: 0;" in section_rule
    assert "overflow-wrap: anywhere;" in section_rule
    assert "width: 100%;" in textarea_rule
    assert "max-width: 100%;" in textarea_rule
    assert "resize: vertical;" in textarea_rule
    assert "box-sizing: border-box;" in editor_rule
    assert "box-sizing: border-box;" in field_rule
    assert "width: 100%;" in field_rule
    assert "display: grid;" in section_editor_rule
    assert "width: 100%;" in section_editor_rule
    assert "overflow-x: auto;" in table_rule


def test_editable_chart_field_has_aligned_wrapper_label_and_textarea_contract() -> None:
    field = reports_page._chart_narrative_field(
        "ranking", "what_shows", cast(Any, "Qué muestra"), "Texto\nmultilínea"
    )
    props = field.to_plotly_json()["props"]
    label, textarea = props["children"]

    assert props["className"] == "reports-chart-editor-field"
    assert label.to_plotly_json()["type"] == "Span"
    assert textarea.className == "reports-chart-narrative"
    assert textarea.value == "Texto\nmultilínea"


def test_chart_narrative_pattern_preserves_multiline_edits_and_empty_values() -> None:
    narratives = reports_page._chart_narratives_from_pattern(
        ["Primera línea\nSegunda línea", "", "Observación revisada"],
        [
            {"chart": "ranking", "field": "what_shows"},
            {"chart": "ranking", "field": "how_to_read"},
            {"chart": "ranking", "field": "observation"},
        ],
    )

    assert narratives == {
        "ranking": {
            "what_shows": "Primera línea\nSegunda línea",
            "how_to_read": "",
            "observation": "Observación revisada",
        }
    }


def test_section_narrative_pattern_preserves_edits_and_rejects_unknown_sections() -> None:
    narratives = reports_page._section_narratives_from_pattern(
        ["Resumen revisado", "", "No permitido"],
        [
            {"section": "executive"},
            {"section": "context"},
            {"section": "methodology"},
        ],
    )

    assert narratives == {"executive": "Resumen revisado", "context": ""}


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
                "context",
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

    report_service.apply_chart_narratives(
        content,
        {
            "ranking": {
                "what_shows": "Texto revisado\npor la persona usuaria",
                "how_to_read": "",
                "observation": "Observación final",
            }
        },
    )
    report_service.apply_section_narratives(
        content,
        {
            "executive": "Resumen ejecutivo revisado",
            "context": "Contexto revisado por la persona usuaria",
            "recommendations": "Primera actuación revisada\nSegunda actuación revisada",
        },
    )

    pdf_bytes = PDFExporter().export(content, chart_paths)
    document = fitz.open(stream=pdf_bytes, filetype="pdf")
    extracted = "\n".join(cast(str, page.get_text()) for page in document)

    assert pdf_bytes.startswith(b"%PDF")
    assert len(document) >= 3
    assert "Informe de diversidad" in extracted
    assert "Resumen ejecutivo" in extracted
    assert "Objetivo del informe" not in extracted
    assert "Posibles líneas de actuación" in extracted
    assert "Resumen ejecutivo revisado" in extracted
    assert "Contexto revisado por la persona usuaria" in extracted
    assert "Primera actuación revisada" in extracted
    assert "Segunda actuación revisada" in extracted
    assert "EU LGBTIQ Survey III, 2023" in extracted
    assert "España" in extracted
    assert "RainbowLens Datahub" in extracted
    assert extracted.index("Resumen ejecutivo") < extracted.index("Métricas principales")
    metadata = document.metadata
    assert metadata is not None
    assert metadata["creator"] == "RainbowLens Datahub"
    assert metadata["producer"] == "RainbowLens Datahub"
    assert "ReportLab" not in " ".join(str(value) for value in metadata.values())
    widgets: list[Any] = [
        cast(Any, widget)
        for page in document
        for widget in (list(page.widgets() or []))
    ]
    widget_values = {widget.field_name: widget.field_value for widget in widgets}
    assert len(widgets) == len(content.charts) * 3
    assert widget_values["chart_ranking_what_shows"] == (
        "Texto revisado\npor la persona usuaria"
    )
    assert widget_values["chart_ranking_how_to_read"] == ""
    assert widget_values["chart_ranking_observation"] == "Observación final"
    assert all(widget.field_type_string == "Text" for widget in widgets)
    assert all(widget.field_flags & 4096 for widget in widgets)
    page_width = document[0].rect.width
    printable_left = 17 * 72 / 25.4
    printable_right = page_width - printable_left
    assert all(widget.rect.x0 >= printable_left - 1 for widget in widgets)
    assert all(widget.rect.x1 <= printable_right + 1 for widget in widgets)
    image_rects = [
        rect
        for page in document
        for image in page.get_images(full=True)
        for rect in page.get_image_rects(image[0])
    ]
    assert image_rects
    assert all(rect.x0 >= printable_left - 1 for rect in image_rects)
    assert all(rect.x1 <= printable_right + 1 for rect in image_rects)


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
    assert user_has_permission(
        SimpleNamespace(is_authenticated=False, role=UserRole.ANONYMOUS),
        Permission.GENERATE_REPORTS,
    )


def test_report_configuration_is_always_hr_focused() -> None:
    custom = {
        **_configuration().to_dict(),
        "profile_key": "admin",
        "detail_level": "detailed",
        "sections": ["executive"],
        "charts": ["ranking"],
    }
    configured = reports_page._hr_report_configuration(custom)

    assert "workplace" in configured.sections
    assert "recommendations" in configured.sections
    assert configured.sections != ("executive",)
    assert configured.detail_level == "standard"
    assert "profile_key" not in configured.to_dict()


def test_server_ignores_legacy_frontend_profile_values() -> None:
    manipulated = {
        **_configuration().to_dict(),
        "profile_key": "admin",
        "source": "fra",
    }

    configured = reports_page._hr_report_configuration(manipulated)

    assert configured.source == "fra"
    assert "profile_key" not in configured.to_dict()


def test_hr_panel_explains_external_context_and_report_generation() -> None:
    panel = reports_page._hr_purpose_panel()

    explanation = next(
        component
        for component in _walk(panel)
        if getattr(component, "className", None) == "reports-hr-explanation"
    )
    assert "informe profesional" in str(explanation)
    assert "contexto externo" in str(panel)
    assert "No constituyen una auditoría" in str(panel)
    assert "Informe orientado a RRHH" in str(panel)


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
        "report-source-select",
        "report-answer-select",
        "report-filter-a-name",
        "report-filters-section",
        "report-indicator-error",
        "report-plan-summary",
    }.issubset(ids)
    assert "report-criterion-select" not in ids
    assert "report-criterion-field" not in ids
    assert "report-objective-select" not in ids
    assert not {
        "report-mode-select",
        "report-sections-select",
        "report-advanced-toggle",
    } & ids
    store_data = getattr(store, "data", None)
    assert isinstance(store_data, dict)
    assert "result" not in store_data
    assert "figure" not in store_data
    source_control = _component_by_id(layout, "report-source-select")
    indicator_control = _component_by_id(layout, "report-indicator-select")
    comparison_control = _component_by_id(layout, "report-comparison-countries")
    assert "report-spanish-context" not in ids
    assert "report-template-select" not in ids
    assert "template_id" not in store_data
    assert [option["value"] for option in source_control.options] == [
        "fra", "ilga", "combined"
    ]
    assert comparison_control.value == ["FR"]
    source_labels = " ".join(str(option["label"].to_plotly_json()) for option in source_control.options)
    assert "Datos sociales" in source_labels
    assert "Datos legales" in source_labels
    assert indicator_control is not None
    assert indicator_control.to_plotly_json()["props"].get("persistence") in {None, False}
    final_actions = next(
        component
        for component in components
        if getattr(component, "className", None) == "reports-actions reports-final-actions"
    )
    assert {
        getattr(component, "id", None) for component in _walk(final_actions)
    } >= {"report-preview-button", "report-download-button"}
    ordered_ids = [getattr(component, "id", None) for component in components]
    assert ordered_ids.index("report-plan-summary") < ordered_ids.index(
        "report-preview-button"
    )
    assert ordered_ids.index("report-preview-button") < ordered_ids.index(
        "report-preview-content"
    )
    assert ordered_ids.index("report-download-button") < ordered_ids.index(
        "report-preview-content"
    )
    assert 'children\': \'FRA\'' not in source_labels


def test_reports_callbacks_register_preview_and_download() -> None:
    app = Dash(__name__, suppress_callback_exceptions=True)
    reports_page.register_reports_callbacks(app)

    keys = "\n".join(app.callback_map)
    assert "report-preview-content.children" in keys
    assert "report-download.data" in keys
    assert "report-config-store.data" in keys
    assert "report-criterion-select" not in str(app.callback_map)
    assert "report-template-select" not in str(app.callback_map)


def test_report_plan_summary_shows_indicator_name_instead_of_internal_code() -> None:
    app = Dash("report-indicator-summary", suppress_callback_exceptions=True)
    reports_page.register_reports_callbacks(app)
    callback = next(
        item["callback"].__wrapped__
        for item in app.callback_map.values()
        if getattr(item.get("callback"), "__wrapped__", None)
        and item["callback"].__wrapped__.__name__ == "update_report_plan_summary"
    )

    summary = callback(
        "fra",
        2023,
        "ES",
        [],
        "Yes",
        "es",
        "Health and mental health",
        "H6_C",
        [
            {
                "label": "Cancer prevention medical checks: last colonoscopy",
                "value": "H6_C",
            }
        ],
        "All",
        "All",
        "All",
        "All",
    )
    rendered_text = " ".join(_collect_text(summary))

    assert "Cancer prevention medical checks: last colonoscopy" in rendered_text
    assert "H6_C" not in rendered_text


def test_social_indicator_validation_and_filter_scope_are_explicit() -> None:
    assert reports_page._missing_social_indicator("fra", "Employment", None)
    assert reports_page._missing_social_indicator("combined", "Employment", None)
    assert not reports_page._missing_social_indicator("fra", "Employment", "EMP_1")
    assert not reports_page._missing_social_indicator("ilga", "Ranking total", None)


def test_dependent_indicator_clears_invalid_values_and_stays_disabled_without_context(
    monkeypatch,
) -> None:
    app = Dash("report-stable-indicator", suppress_callback_exceptions=True)
    reports_page.register_reports_callbacks(app)
    callback = next(
        item["callback"].__wrapped__
        for item in app.callback_map.values()
        if getattr(item.get("callback"), "__wrapped__", None)
        and item["callback"].__wrapped__.__name__ == "update_report_indicators"
    )
    monkeypatch.setattr(
        reports_page,
        "_indicator_options",
        lambda source, category, _year: (
            [{"label": "B1", "value": "B1"}]
            if source == "fra" and category == "Category B"
            else []
        ),
    )

    assert callback("fra", "", 2023, "A1") == ([], None, True)
    assert callback("fra", "Category B", 2023, "A1") == (
        [{"label": "B1", "value": "B1"}],
        None,
        False,
    )
    assert callback("ilga", "Ranking total", 2026, "B1") == ([], None, True)


def test_legal_source_hides_and_clears_social_filters(monkeypatch) -> None:
    app = Dash("report-legal-control-scope", suppress_callback_exceptions=True)
    reports_page.register_reports_callbacks(app)
    callback = next(
        item["callback"].__wrapped__
        for item in app.callback_map.values()
        if getattr(item.get("callback"), "__wrapped__", None)
        and item["callback"].__wrapped__.__name__ == "update_report_social_controls"
    )
    monkeypatch.setattr(
        reports_page,
        "get_fra_control_payload",
        lambda *_args: (_ for _ in ()).throw(AssertionError("unexpected FRA query")),
    )

    result = callback(
        "ilga",
        None,
        "Ranking total",
        2026,
        "Yes",
        "Age",
        "25-39",
        "Gender identity",
        "Trans woman",
    )

    assert result[0:5] == (
        [],
        None,
        True,
        "reports-field is-hidden",
        "reports-filters-section is-hidden",
    )
    assert result[6] == "All"
    assert result[9] == "All"
    assert result[12] == "All"
    assert result[15] == "All"


def test_preview_is_blocked_when_social_indicator_is_missing() -> None:
    app = Dash("report-required-indicator", suppress_callback_exceptions=True)
    reports_page.register_reports_callbacks(app)
    callback = next(
        item["callback"].__wrapped__
        for item in app.callback_map.values()
        if getattr(item.get("callback"), "__wrapped__", None)
        and item["callback"].__wrapped__.__name__ == "preview_report"
    )

    result = callback(
        1,
        "Informe",
        None,
        None,
        "fra",
        "Employment",
        None,
        2023,
        "ES",
        [],
        "es",
        None,
        "All",
        "All",
        "All",
        "All",
        "2026-08-21",
        {},
    )

    assert result[2] == "Selecciona un indicador social para continuar."
    assert result[3] == "reports-status reports-status-error"
    assert result[5] is True


def test_report_route_params_keep_only_lightweight_whitelisted_filters() -> None:
    parsed = _report_params(
        {
            "source": ["fra"],
            "indicator_id": ["EMP_1"],
            "countries": ["ES,FR"],
            "frames": ['[{"large": "payload"}]'],
            "password": ["secret"],
        }
    )

    assert parsed == {
        "source": "fra",
        "indicator_id": "EMP_1",
        "countries": ["ES", "FR"],
    }


def test_render_dependencies_install_plotly_chrome() -> None:
    root = Path(__file__).resolve().parents[3]
    render_config = (root / "render.yaml").read_text(encoding="utf-8")
    requirements = (root / "requirements.txt").read_text(encoding="utf-8")

    build_script = (root / "scripts" / "render_build.sh").read_text(encoding="utf-8")
    start_script = (root / "scripts" / "render_start.sh").read_text(encoding="utf-8")

    assert "bash scripts/render_build.sh" in render_config
    assert "bash scripts/render_start.sh" in render_config
    assert 'browser_root="${venv_root}/kaleido-chrome"' in build_script
    assert 'plotly_get_chrome -y --path "${browser_root}"' in build_script
    assert "plotly_get_chrome --help || true" in build_script
    assert 'test -x "${BROWSER_PATH}"' in build_script
    assert "chart_export_build browser_headless=PASS" in build_script
    assert "browser_headless=INCONCLUSIVE reason=standalone_probe_failed" in build_script
    assert "python scripts/check_chart_export.py" in build_script
    assert "python scripts/check_chart_export.py --single-only" in start_script
    assert "exec gunicorn wsgi:server" in start_script
    assert "kaleido==1.3.0" in requirements
    assert "choreographer==1.3.0" in requirements
    assert "reportlab==4.5.1" in requirements
    assert "healthCheckPath: /health" in render_config
    assert "type: keyvalue" not in render_config
    assert "LOCAL_CACHE_MAX_ENTRIES" in render_config
    assert "LOCAL_CACHE_MAX_TOTAL_BYTES" in render_config


def test_report_export_finds_bundled_chrome_when_environment_path_is_stale(
    tmp_path: Path,
    monkeypatch,
) -> None:
    browser = tmp_path / "kaleido-chrome" / "chrome-linux64" / "chrome"
    browser.parent.mkdir(parents=True)
    browser.write_bytes(b"chrome")
    browser.chmod(0o755)
    monkeypatch.setenv("BROWSER_PATH", "/missing/old-render-chrome")

    configured = _configure_kaleido_browser(tmp_path)

    assert configured == str(browser.resolve())
    assert os.environ["BROWSER_PATH"] == str(browser.resolve())


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
