from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import fitz
import plotly.graph_objects as go
import pytest
from dash import Dash, dcc
from PIL import Image

from app.core.auth.permissions import Permission, user_has_permission
from app.modules.account.users.schemas import UserRole
from app.modules.reports import builder as report_builder
from app.modules.reports import page as reports_page
from app.modules.reports import service as report_service
from app.modules.reports import static_charts
from app.modules.reports.builder import HRReportBuilder
from app.modules.reports.models import (
    ReportConfiguration,
    ReportDataset,
    sanitize_report_text,
)
from app.modules.reports.pdf_exporter import PDFExporter
from app.modules.reports.static_charts import ReportChartRenderer
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


@pytest.mark.parametrize("language,label", [("es", "Sin datos"), ("en", "No data")])
def test_legal_pdf_figures_and_missing_data_legend_use_report_language(
    monkeypatch, tmp_path, language, label
):
    from PIL import ImageDraw

    configuration = _configuration(source="ilga", category="Ranking total", language=language)
    content = HRReportBuilder().build(configuration, ReportDataset(_ilga_result(), query_seconds=0))
    figure = next(chart.figure for chart in content.charts if chart.key.startswith("map_"))
    assert figure is not None
    if language == "en":
        assert "Ranking total" not in str(figure.layout.title.text)
    drawn = []
    original = ImageDraw.ImageDraw.text

    def draw_text(self, xy, text, *args, **kwargs):
        drawn.append(text)
        return original(self, xy, text, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", draw_text)
    target = tmp_path / "map.png"
    with ReportChartRenderer() as renderer:
        renderer.write("map", figure, target)
    assert target.stat().st_size > 1000
    assert label in drawn
    assert ("Sin datos" if language == "en" else "No data") not in drawn


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


def _combined_result() -> dict[str, Any]:
    result = _fra_result()
    rows = [
        {"country": "España", "iso": "ES", "fra_value": 64.0, "ilga_value": 78.0},
        {"country": "Francia", "iso": "FR", "fra_value": 55.0, "ilga_value": 69.0},
        {"country": "Alemania", "iso": "DE", "fra_value": 49.0, "ilga_value": 61.0},
    ]
    ranking_gap = {
        "available": True,
        "rows": [
            {
                **row,
                "fra_rank": index,
                "ilga_rank": index,
                "absolute_rank_difference": 0,
            }
            for index, row in enumerate(rows, start=1)
        ],
    }
    result.update(
        {
            "source": "FRA + ILGA-Europe",
            "combined_analysis": {
                "status": "ok",
                "rows": rows,
                "metrics": {},
                "semantics": {"direction": "higher_is_better"},
                "supported_analyses": {"ranking_gap": True},
                "fra_year": 2024,
                "ilga_year": 2026,
                "ranking_gap": ranking_gap,
            },
            "ranking_gap": ranking_gap,
        }
    )
    return result


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
        ("AL", "Albania"),
        ("AD", "Andorra"),
        ("AM", "Armenia"),
        ("AZ", "Azerbaijan"),
        ("BA", "Bosnia and Herzegovina"),
        ("BG", "Bulgaria"),
        ("HR", "Croatia"),
        ("CY", "Cyprus"),
        ("DK", "Denmark"),
        ("EE", "Estonia"),
        ("GE", "Georgia"),
        ("GR", "Greece"),
        ("HU", "Hungary"),
        ("IS", "Iceland"),
        ("IE", "Ireland"),
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
            "generated_on": "2000-01-01",
        }
    )

    assert config.title == "alert(1) Informe"
    assert config.organization == "Empresa"
    assert config.countries == ("ES", "DE")
    assert config.primary_country == "ES"
    assert config.sections == ("metrics", "sources")
    assert config.charts == ("ranking",)
    assert config.year == 2024
    assert "generated_on" not in config.to_dict()
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
    assert config.charts == ("ranking", "responses")


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
    assert len(content.charts) == 3
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
        ReportConfiguration.from_mapping({"source": "ilga", "year": 2026, "language": "es"}),
        ReportDataset(_ilga_result(), query_seconds=0.01),
    )

    assert social.charts[0].key == "map_fra"
    social_map = social.charts[0].figure
    assert social_map is not None
    assert cast(Any, social_map.data[0]).type == "choropleth"
    assert legal.charts[0].key == "map_ilga"
    legal_map = legal.charts[0].figure
    assert legal_map is not None
    assert cast(Any, legal_map.data[0]).type == "choropleth"


def test_combined_preview_contains_both_maps_and_valid_plotly_figures() -> None:
    configuration = ReportConfiguration.from_mapping(
        {
            "source": "combined",
            "year": 2024,
            "charts": ["scatter", "ranking_gap"],
            "countries": [],
            "language": "es",
        }
    )
    content = HRReportBuilder().build(
        configuration,
        ReportDataset(_combined_result(), query_seconds=0.01),
    )
    graphs = [
        item
        for component in reports_page._preview_content(content)
        for item in _walk(component)
        if isinstance(item, dcc.Graph)
    ]

    assert [chart.key for chart in content.charts] == [
        "map_fra",
        "map_ilga",
        "scatter",
        "ranking_gap",
    ]
    assert all(
        isinstance(figure, go.Figure) for chart in content.charts for figure in chart.figures
    )
    assert len(graphs) == sum(len(chart.figures) for chart in content.charts)
    assert all(isinstance(getattr(graph, "figure", None), go.Figure) for graph in graphs)


def test_combined_pdf_renders_numeric_and_categorical_scatter_charts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configuration = ReportConfiguration.from_mapping(
        {
            "source": "combined",
            "year": 2024,
            "charts": ["scatter", "quadrants", "ranking_gap"],
            "countries": [],
            "language": "es",
        }
    )
    monkeypatch.setattr(
        report_service,
        "load_report_dataset",
        lambda _configuration: ReportDataset(_combined_result(), query_seconds=0.01),
    )

    generated = report_service.generate_report_pdf(configuration)

    assert [chart.key for chart in generated.content.charts] == [
        "map_fra",
        "map_ilga",
        "scatter",
        "ranking_gap",
    ]
    assert generated.image_count == 4
    assert generated.pdf_bytes.startswith(b"%PDF")


def test_unselected_ranking_uses_one_pdf_figure_without_losing_countries() -> None:
    content = HRReportBuilder().build(
        _configuration(countries=[], primary_country="", charts=["ranking"]),
        ReportDataset(_many_country_result(), query_seconds=0.01),
    )
    ranking = next(chart for chart in content.charts if chart.key == "ranking")
    page_countries = [
        str(country) for figure in ranking.figures for country in cast(Any, figure.data[0]).y
    ]

    assert len(ranking.figures) == 1
    assert ranking.page_ranges == [(1, 12)]
    assert [len(cast(Any, figure.data[0]).y) for figure in ranking.figures] == [12]
    assert len(page_countries) == len(set(page_countries)) == 12
    assert len(content.table_rows) == 12


def test_preview_uses_one_complete_ranking_when_no_countries_are_selected() -> None:
    content = HRReportBuilder().build(
        _configuration(countries=[], primary_country="", charts=["ranking"]),
        ReportDataset(_many_country_result(27), query_seconds=0.01),
    )
    ranking = next(chart for chart in content.charts if chart.key == "ranking")
    assert ranking.figure is not None
    rendered = [str(country) for country in cast(Any, ranking.figure.data[0]).y]

    assert len(ranking.figures) == 1
    assert len(rendered) == len(set(rendered)) == 27
    assert set(rendered) == {row["country"] for row in content.table_rows}


def test_pdf_ranking_pages_stream_ten_ten_seven_without_loss_or_duplicates() -> None:
    result = _many_country_result(27)
    result["ranking"][10]["value"] = result["ranking"][9]["value"]
    tied_codes = {result["ranking"][9]["iso"], result["ranking"][10]["iso"]}
    rendered_pages: list[list[str]] = []
    positions: dict[str, str] = {}

    def consume(key: str, _page: int, figure: go.Figure) -> None:
        if key != "ranking":
            return
        countries = [str(country) for country in cast(Any, figure.data[0]).y]
        rendered_pages.append(countries)
        positions.update(
            {str(custom[0]): str(custom[1]) for custom in cast(Any, figure.data[0]).customdata}
        )

    content = HRReportBuilder().build_for_pdf(
        _configuration(countries=[], primary_country="", charts=["ranking"]),
        ReportDataset(result, query_seconds=0.01),
        consume,
    )
    ranking = next(chart for chart in content.charts if chart.key == "ranking")
    rendered = [country for page in rendered_pages for country in page]
    expected = {str(row["country"]) for row in content.table_rows}

    assert [len(page) for page in rendered_pages] == [10, 10, 7]
    assert ranking.page_ranges == [(1, 10), (11, 20), (21, 27)]
    assert set(rendered) == expected
    assert len(rendered) == len(set(rendered))
    assert positions["ES"] == "1"
    assert positions["IE"] == "27"
    assert {positions[code] for code in tied_codes} == {"10"}
    assert not ranking.figures


def test_report_keeps_real_zero_and_excludes_missing_country_values() -> None:
    result = _fra_result()
    result["ranking"][2]["value"] = 0.0
    content = HRReportBuilder().build(
        _configuration(countries=[], primary_country="", charts=["ranking"]),
        ReportDataset(result, query_seconds=0.01),
    )

    values = {row["country"]: row["value"] for row in content.table_rows}

    assert 0.0 in values.values()
    assert len(values) == 3
    assert all("Portugal" not in country for country in values)


def test_other_multi_country_figures_use_one_static_pdf_scope() -> None:
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
    assert len(figures["countries"].figures) == 1
    assert len(figures["responses"].figures) == 1
    assert figures["countries"].page_ranges == [(1, 12)]
    response_page_countries = [
        {str(country) for trace in figure.data for country in (getattr(trace, "y", None) or [])}
        for figure in figures["responses"].figures
    ]
    assert [len(countries) for countries in response_page_countries] == [12]
    assert all(not figure.layout.annotations for figure in figures["responses"].figures)


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
    response_figure = responses.figure
    assert response_figure is not None
    rendered_countries = {
        str(country)
        for trace in response_figure.data
        for country in (getattr(trace, "y", None) or [])
    }

    assert len(responses.figures) == 1
    assert rendered_countries == {"España", "Alemania"}
    assert len(response_figure.layout.annotations) == 2
    assert {annotation.text for annotation in response_figure.layout.annotations} == {
        "Seleccionado"
    }


def test_selected_ranking_only_contains_explicit_countries() -> None:
    selected = ["ES", "FR", "DE"]
    content = HRReportBuilder().build(
        _configuration(countries=selected, primary_country="ES", charts=["ranking"]),
        ReportDataset(_many_country_result(), query_seconds=0.01),
    )
    ranking = next(chart for chart in content.charts if chart.key == "ranking")
    ranking_figure = ranking.figure
    assert ranking_figure is not None
    countries = set(cast(Any, ranking_figure.data[0]).y)

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
        str(item[1]) for figure in ranking.figures for item in cast(Any, figure.data[0]).customdata
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
    chart_textareas = [item for item in textareas if item.id["type"] == "report-chart-narrative"]
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
    assert all(isinstance(getattr(graph, "figure", None), go.Figure) for graph in graphs)
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
        Path(__file__).resolve().parents[3] / "src" / "app" / "web" / "assets" / "reports.css"
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


def test_report_dataset_exposes_statistics_timings(monkeypatch) -> None:
    result = _fra_result()
    result["_statistics_timings"] = {
        "query_ms": 12.0,
        "normalization_ms": 8.0,
        "analysis_ms": 5.0,
        "cache_hit": True,
    }
    monkeypatch.setattr(report_service, "get_fra_statistics", lambda _query: result)

    dataset = report_service.load_report_dataset(_configuration())

    assert dataset.normalization_seconds == 0.008
    assert dataset.analysis_seconds == 0.005
    assert dataset.cache_hit is True


def test_server_png_export_is_valid_and_document_resolution() -> None:
    image_path = Path("tmp/pdfs/test-report-chart.png")
    image_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with ReportChartRenderer(width=800, height=450) as renderer:
            renderer.write(
                "ranking",
                go.Figure(go.Bar(x=["España", "Francia"], y=[64, 55])),
                image_path,
            )
        with Image.open(image_path) as image:
            assert image.format == "PNG"
            assert image.size == (800, 450)
    finally:
        image_path.unlink(missing_ok=True)


def test_report_renderer_does_not_mutate_interactive_selection_annotations(tmp_path: Path) -> None:
    figure = go.Figure(go.Bar(x=[64], y=["España"], orientation="h"))
    figure.add_annotation(text="Seleccionado", x=1, y="España")

    with ReportChartRenderer() as renderer:
        renderer.write("ranking", figure, tmp_path / "ranking.png")

    assert [annotation.text for annotation in figure.layout.annotations] == ["Seleccionado"]


def test_pdf_export_contains_sections_charts_and_automatic_generation_date(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.modules.reports.pdf_exporter.utc_today_iso",
        lambda: "2026-09-04",
    )
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
    with ReportChartRenderer(width=1000, height=560) as renderer:
        for chart in content.charts:
            path = tmp_path / f"{chart.key}.png"
            figure = chart.figure
            assert figure is not None
            renderer.write(chart.key, figure, path)
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
    assert "2026-09-04" in extracted
    assert extracted.index("Resumen ejecutivo") < extracted.index("Métricas principales")
    metadata = document.metadata
    assert metadata is not None
    assert metadata["creator"] == "RainbowLens Datahub"
    assert metadata["producer"] == "RainbowLens Datahub"
    assert "ReportLab" not in " ".join(str(value) for value in metadata.values())
    widgets: list[Any] = [
        cast(Any, widget) for page in document for widget in (list(page.widgets() or []))
    ]
    widget_values = {widget.field_name: widget.field_value for widget in widgets}
    assert len(widgets) == len(content.charts) * 3
    assert widget_values["chart_ranking_what_shows"] == ("Texto revisado\npor la persona usuaria")
    assert widget_values["chart_ranking_how_to_read"] == ""
    assert widget_values["chart_ranking_observation"] == "Observación final"
    assert all(widget.field_type_string == "Text" for widget in widgets)
    assert all(widget.field_flags & 4096 for widget in widgets)
    page_width = document[0].rect.width
    printable_left = 17 * 72 / 25.4
    printable_right = page_width - printable_left
    assert all(widget.rect.x0 >= printable_left - 1 for widget in widgets)
    assert all(widget.rect.x1 <= printable_right + 1 for widget in widgets)
    for page in document:
        for widget in page.widgets() or ():
            if cast(Any, widget).field_name != "chart_ranking_what_shows":
                continue
            words = page.get_text("words", clip=widget.rect)
            assert "persona" in {word[4] for word in words}
            assert len({round(float(word[1]), 1) for word in words}) >= 2
    image_rects = [
        rect
        for page in document
        for image in page.get_images(full=True)
        for rect in page.get_image_rects(image[0])
    ]
    assert image_rects
    assert all(rect.x0 >= printable_left - 1 for rect in image_rects)
    assert all(rect.x1 <= printable_right + 1 for rect in image_rects)


@pytest.mark.parametrize("failure_stage", [None, "chart", "pdf"])
def test_generate_report_cleans_temporary_directory(monkeypatch, failure_stage) -> None:
    observed_roots: list[Path] = []

    monkeypatch.setattr(
        report_service,
        "load_report_dataset",
        lambda _config: ReportDataset(_fra_result(), query_seconds=0.01),
    )

    class FakeExporter:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def write(self, _key, _figure, path_value):
            path = Path(path_value)
            observed_roots.append(path.parent)
            path.write_bytes(b"png")
            if failure_stage == "chart":
                raise static_charts.ReportChartRenderError("test-render-failure")
            return path

    monkeypatch.setattr(report_service, "ReportChartRenderer", FakeExporter)

    def export_pdf(_self, _content, _images):
        if failure_stage == "pdf":
            raise RuntimeError("test-pdf-failure")
        return b"%PDF-test"

    monkeypatch.setattr(report_service.PDFExporter, "export", export_pdf)

    if failure_stage:
        with pytest.raises(report_service.ReportGenerationError):
            report_service.generate_report_pdf(_configuration())
        assert observed_roots
        assert all(not root.exists() for root in observed_roots)
        return

    generated = report_service.generate_report_pdf(_configuration())

    assert generated.pdf_bytes == b"%PDF-test"
    assert generated.filename.endswith(".pdf")
    assert observed_roots
    assert all(not root.exists() for root in observed_roots)

    second = report_service.generate_report_pdf(_configuration())
    assert second.pdf_bytes == b"%PDF-test"
    assert all(not root.exists() for root in observed_roots)


def test_report_closes_image_when_drawing_fails(monkeypatch, tmp_path: Path) -> None:
    allocated = Image.new("RGB", (100, 100))
    monkeypatch.setattr(static_charts.Image, "new", lambda *_args: allocated)

    def fail_drawing(*_args):
        raise ValueError("test-drawing-failure")

    monkeypatch.setattr(static_charts, "_draw_title", fail_drawing)
    with pytest.raises(static_charts.ReportChartRenderError):
        ReportChartRenderer().write("ranking", go.Figure(), tmp_path / "failed.png")
    with pytest.raises(ValueError, match="closed image"):
        allocated.getpixel((0, 0))


def test_preview_and_pdf_build_each_report_figure_only_once(monkeypatch) -> None:
    configuration = _configuration(countries=[], primary_country="")
    calls = {"map": 0, "ranking": 0, "responses": 0}
    export_calls = 0

    def tracked_figure(name: str):
        def build(*_args, **_kwargs):
            calls[name] += 1
            return go.Figure(go.Bar(x=["A"], y=[1]))

        return build

    monkeypatch.setattr(
        report_service,
        "load_report_dataset",
        lambda _config: ReportDataset(_fra_result(), query_seconds=0.01),
    )
    monkeypatch.setattr(report_builder, "build_europe_choropleth", tracked_figure("map"))
    monkeypatch.setattr(
        report_builder,
        "build_comparative_ranking_chart",
        tracked_figure("ranking"),
    )
    monkeypatch.setattr(
        report_builder,
        "build_fra_response_comparison_chart",
        tracked_figure("responses"),
    )

    class FakeExporter:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def write(self, _key, _figure, target):
            nonlocal export_calls
            export_calls += 1
            target = Path(target)
            target.write_bytes(b"png")
            return target

    monkeypatch.setattr(report_service, "ReportChartRenderer", FakeExporter)

    preview = report_service.build_report_preview(configuration)

    assert calls == {"map": 1, "ranking": 1, "responses": 1}
    assert all(chart.figures for chart in preview.charts)
    assert export_calls == 0

    def fake_pdf(_self, content, _images):
        ranking = next(chart for chart in content.charts if chart.key == "ranking")
        assert ranking.what_shows == "Texto editado"
        assert content.section_narratives["executive"] == "Resumen editado"
        return b"%PDF-test"

    monkeypatch.setattr(report_service.PDFExporter, "export", fake_pdf)

    generated = report_service.generate_report_pdf(
        configuration,
        chart_narratives={"ranking": {"what_shows": "Texto editado"}},
        section_narratives={"executive": "Resumen editado"},
    )

    assert calls == {"map": 2, "ranking": 2, "responses": 2}
    assert export_calls == 3
    assert generated.image_count == 3
    assert all(not chart.figures for chart in generated.content.charts)


def test_preview_converts_chart_failures_to_controlled_errors(monkeypatch) -> None:
    monkeypatch.setattr(
        report_service,
        "load_report_dataset",
        lambda _config: ReportDataset(_fra_result(), query_seconds=0.01),
    )

    def fail_chart(*_args, **_kwargs):
        raise RuntimeError("chart failed")

    monkeypatch.setattr(report_builder, "build_europe_choropleth", fail_chart)

    with pytest.raises(report_service.ReportGenerationError):
        report_service.build_report_preview(_configuration())


def test_report_generation_lock_prevents_overlapping_exports(monkeypatch) -> None:
    active = 0
    maximum_active = 0
    state_lock = threading.Lock()

    def fake_generate(configuration, **_kwargs):
        nonlocal active, maximum_active
        with state_lock:
            active += 1
            maximum_active = max(maximum_active, active)
        time.sleep(0.04)
        with state_lock:
            active -= 1
        return configuration

    monkeypatch.setattr(report_service, "_generate_report_pdf", fake_generate)
    configuration = _configuration()
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(report_service.generate_report_pdf, [configuration] * 2))

    assert results == [configuration, configuration]
    assert maximum_active == 1


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
        "report-download-loading",
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
    assert (
        not {
            "report-mode-select",
            "report-sections-select",
            "report-advanced-toggle",
        }
        & ids
    )
    store_data = getattr(store, "data", None)
    assert isinstance(store_data, dict)
    assert "result" not in store_data
    assert "figure" not in store_data
    source_control = _component_by_id(layout, "report-source-select")
    indicator_control = _component_by_id(layout, "report-indicator-select")
    comparison_control = _component_by_id(layout, "report-comparison-countries")
    assert "report-spanish-context" not in ids
    assert "report-template-select" not in ids
    assert "report-generated-on" not in ids
    assert "template_id" not in store_data
    assert [option["value"] for option in source_control.options] == ["fra", "ilga", "combined"]
    assert comparison_control.value == ["FR"]
    source_labels = " ".join(
        str(option["label"].to_plotly_json()) for option in source_control.options
    )
    assert "Datos sociales" in source_labels
    assert "Datos legales" in source_labels
    assert indicator_control is not None
    download_loading = _component_by_id(layout, "report-download-loading")
    assert download_loading.target_components == {"report-download": "data"}
    assert indicator_control.to_plotly_json()["props"].get("persistence") in {None, False}
    final_actions = next(
        component
        for component in components
        if getattr(component, "className", None) == "reports-actions reports-final-actions"
    )
    assert {getattr(component, "id", None) for component in _walk(final_actions)} >= {
        "report-preview-button",
        "report-download-button",
    }
    ordered_ids = [getattr(component, "id", None) for component in components]
    assert ordered_ids.index("report-plan-summary") < ordered_ids.index("report-preview-button")
    assert ordered_ids.index("report-preview-button") < ordered_ids.index("report-preview-content")
    assert ordered_ids.index("report-download-button") < ordered_ids.index("report-preview-content")
    assert "children': 'FRA'" not in source_labels


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
    assert "Salud y salud mental" in rendered_text
    legal = callback(
        "ilga", 2026, None, [], None, "en", "Ranking total", None, [], "All", "All", "All", "All"
    )
    assert "Overall ranking" in " ".join(_collect_text(legal))
    assert "Ranking total" not in " ".join(_collect_text(legal))


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
            [{"label": "B1", "value": "B1"}] if source == "fra" and category == "Category B" else []
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
        "Age",
        "Gender identity",
        "Yes",
        "25-39",
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


def test_report_filter_changes_refresh_values_and_exclusive_filter_state(monkeypatch) -> None:
    app = Dash("report-filter-interaction", suppress_callback_exceptions=True)
    reports_page.register_reports_callbacks(app)
    registration = next(
        item
        for item in app.callback_map.values()
        if getattr(item.get("callback"), "__wrapped__", None)
        and item["callback"].__wrapped__.__name__ == "update_report_social_controls"
    )
    input_ids = {item["id"] for item in registration["inputs"]}
    assert {"report-filter-a-name", "report-filter-b-name"} <= input_ids
    age_options = [{"label": "25-39", "value": "25-39"}]
    monkeypatch.setattr(
        reports_page,
        "get_fra_control_payload",
        lambda *_args: {
            "answers": [{"label": "Yes", "value": "Yes"}],
            "default_answer": "Yes",
            "segmentations": [
                {"label": "All", "value": "All"},
                {"label": "Age", "value": "Age"},
            ],
            "values": {"All": [{"label": "All", "value": "All"}], "Age": age_options},
        },
    )
    callback = registration["callback"].__wrapped__
    primary = callback("fra", "EMP_1", "Discrimination", 2023, "Age", "Age", "Yes", "All", "25-39")
    assert [option["value"] for option in primary[8]] == ["25-39"]
    assert primary[10] is False
    assert primary[12] == "All"
    assert primary[13] is True
    assert primary[16] is True

    secondary = callback("fra", "EMP_1", "Discrimination", 2023, "All", "Age", "Yes", "All", "All")
    assert secondary[10] is True
    assert [option["value"] for option in secondary[14]] == ["25-39"]
    assert secondary[13] is False
    assert secondary[16] is False


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
            "generated_on": ["2000-01-01"],
            "frames": ['[{"large": "payload"}]'],
            "password": ["secret"],
        }
    )

    assert parsed == {
        "source": "fra",
        "indicator_id": "EMP_1",
        "countries": ["ES", "FR"],
    }


def test_render_installs_application_and_starts_gunicorn() -> None:
    root = Path(__file__).resolve().parents[3]
    render_config = (root / "render.yaml").read_text(encoding="utf-8")

    build_script = (root / "scripts" / "render_build.sh").read_text(encoding="utf-8")
    start_script = (root / "scripts" / "render_start.sh").read_text(encoding="utf-8")

    assert "bash scripts/render_build.sh" in render_config
    assert "bash scripts/render_start.sh" in render_config
    assert "python -m pip install -e ." in build_script
    assert "exec gunicorn wsgi:server" in start_script
    assert "healthCheckPath: /health" in render_config
    assert "type: keyvalue" not in render_config
    assert "LOCAL_CACHE_MAX_ENTRIES" in render_config
    assert "LOCAL_CACHE_MAX_TOTAL_BYTES" in render_config
    assert 'value: "256"' in render_config
    assert 'value: "16777216"' in render_config


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
