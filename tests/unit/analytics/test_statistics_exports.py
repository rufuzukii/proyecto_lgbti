from __future__ import annotations

import csv
import io
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, cast

import plotly.graph_objects as go
import pytest

from app.analytics.statistics_exports import (
    EXPORT_FILENAME_MAX_LENGTH,
    EXPORT_FORMAT,
    EXPORT_HEIGHT,
    EXPORT_SCALE,
    EXPORT_WIDTH,
    build_export_filename,
    chart_graph_config,
    export_summary_table,
    prepare_figure_for_export,
)
from app.dash.pages.statistics import _render_dashboard, build_statistics_layout

ROOT = Path(__file__).resolve().parents[3]


def test_export_filename_is_descriptive_safe_and_bounded() -> None:
    filename = build_export_filename(
        "Ranking comparativo",
        "Discriminación en el empleo / promoción",
        ["España", "França"],
        2024,
    )
    malicious = build_export_filename(
        "../../<script>alert(1)</script>",
        "A" * 400,
        ["../../España"],
        "2024/25",
    )

    assert filename == (
        "rainbowlens-datahub_ranking-comparativo_discriminacion-en-el-empleo-promocion_"
        "espana-franca_2024.png"
    )
    assert malicious.endswith(".png")
    assert ".." not in malicious
    assert "<" not in malicious
    assert "/" not in malicious
    assert len(malicious) <= EXPORT_FILENAME_MAX_LENGTH


def test_statistics_css_allows_dynamic_graphs_to_grow_before_footer() -> None:
    css = (ROOT / "src/app/dash/assets/statistics.css").read_text(encoding="utf-8")

    assert ".stats-response-panel {" in css
    assert "min-height: 520px;" in css
    assert ".stats-response-panel .dash-graph" in css
    assert ".stats-panel-wrapper > .stats-panel {\n  height: auto;" in css
    assert ".stats-results-table-panel {\n  overflow: hidden;" in css


def test_statistics_css_has_full_width_ranking_and_mobile_boundaries() -> None:
    css = (ROOT / "src/app/dash/assets/statistics.css").read_text(encoding="utf-8")

    assert ".stats-ranking-panel,\n.stats-response-comparison-section," in css
    assert ".stats-response-comparison-scroll {" in css
    assert "  grid-column: 1 / -1;" in css
    assert "@media (min-width: 768px) and (max-width: 1199px)" in css
    assert "@media (max-width: 767px)" in css
    assert "@media (max-width: 480px)" in css
    assert ".stats-grid {\n    gap: 0.85rem;\n    grid-template-columns: minmax(0, 1fr);" in css
    assert ".stats-results-table-scroll {\n  max-width: 100%;" in css
    assert "overflow-x: auto;" in css
    assert ".stats-results-grid {\n    min-width: 680px;" in css
    assert ".stats-mapbox-graph {\n    height: min(58vh, 460px);\n    min-height: 340px;" in css
    assert "height: clamp(520px, 66vh, 680px);" in css
    assert "overflow-x: hidden" not in css


def test_create_report_button_uses_theme_specific_text_colours() -> None:
    css = (ROOT / "src/app/dash/assets/statistics.css").read_text(encoding="utf-8")
    reports_css = (ROOT / "src/app/dash/assets/reports.css").read_text(encoding="utf-8")

    assert ".stats-create-report-link {" in css
    assert "  color: #000;" in css
    assert 'body[data-theme="dark"] .stats-create-report-link,' in css
    assert "  color: #fff;" in css
    assert ".stats-create-report-link:active" in css
    assert '.stats-create-report-link[aria-disabled="true"]' in css
    assert ".stats-create-report-link" not in reports_css


def test_summary_table_csv_uses_visible_columns_order_bom_and_safe_values() -> None:
    table_export = export_summary_table(
        [
            {
                "country": "Espa\u00f1a",
                "value": 63.5,
                "year": 2024,
                "indicator": "Discriminaci\u00f3n",
                "status": "Disponible",
                "_id": "secret",
            },
            {
                "country": '=HYPERLINK("https://invalid")',
                "value": -2.5,
                "year": 2024,
                "indicator": "Seguridad",
                "status": "Sin datos",
            },
        ],
        [
            {"field": "country", "headerName": "Pa\u00eds"},
            {"field": "value", "headerName": "Valor (%)"},
            {"field": "year", "headerName": "A\u00f1o"},
            {"field": "indicator", "headerName": "Indicador"},
            {"field": "status", "headerName": "Estado"},
            {"field": "_id", "headerName": "Internal"},
        ],
        language="es",
        metadata={
            "indicator": "Discriminaci\u00f3n",
            "year": 2024,
            "countries": [],
            "source": "FRA",
        },
    )

    assert table_export.content.startswith("\ufeff")
    parsed = list(csv.reader(io.StringIO(table_export.content.lstrip("\ufeff")), delimiter=";"))
    assert parsed[0] == ["Pa\u00eds", "Valor (%)", "A\u00f1o", "Indicador", "Estado"]
    assert parsed[1] == ["Espa\u00f1a", "63.5", "2024", "Discriminaci\u00f3n", "Disponible"]
    assert parsed[2][0].startswith("'=")
    assert parsed[2][1] == "-2.5"
    assert all("secret" not in row for row in parsed)
    assert any("EU LGBTIQ Survey III, 2023" in " ".join(row) for row in parsed)
    assert any("fra.europa.eu" in " ".join(row) for row in parsed)
    assert table_export.filename == (
        "rainbowlens-datahub_tabla-resumida_discriminacion_europa_2024.csv"
    )
    assert table_export.mime_type == "text/csv;charset=utf-8"


def test_summary_table_csv_preserves_english_headers_and_rejects_empty_data() -> None:
    table_export = export_summary_table(
        [{"country": "Spain", "value": 63.5}],
        [
            {"field": "country", "headerName": "Country"},
            {"field": "value", "headerName": "Value (%)"},
        ],
        language="en",
        metadata={"indicator": "Discrimination", "year": 2024, "countries": ["Spain"]},
    )

    assert "Country;Value (%)" in table_export.content
    assert table_export.filename.endswith("_spain_2024.csv")
    with pytest.raises(ValueError, match="rows are required"):
        export_summary_table([], [], language="en", metadata={})


def test_export_metadata_keeps_current_context_and_document_resolution() -> None:
    figure = go.Figure(go.Bar(x=["Spain"], y=[63]))

    prepared = prepare_figure_for_export(
        figure,
        chart_type="ranking",
        chart_title="Ranking comparativo",
        indicator="Discriminación en el empleo",
        countries=["España", "Francia"],
        year=2024,
        source="FRA",
        filters=["Respuesta: Yes", "Edad: 25-39"],
        language="es",
    )

    layout = cast(Any, prepared).layout
    assert prepared is figure
    assert layout.meta["export_format"] == EXPORT_FORMAT
    assert layout.meta["export_width"] == EXPORT_WIDTH
    assert layout.meta["export_height"] == EXPORT_HEIGHT
    assert layout.meta["export_scale"] == EXPORT_SCALE
    assert layout.meta["export_filename"].endswith("_espana-francia_2024.png")
    assert "Discriminación en el empleo" in layout.title.text
    assert "Fuente: FRA, EU LGBTIQ Survey III, 2023" in layout.title.text
    assert "RainbowLens Datahub" in layout.title.text
    assert "Respuesta: Yes" in layout.title.text
    assert layout.margin.t >= 82


def test_long_chart_summary_wraps_without_truncating_the_attribution() -> None:
    figure = go.Figure(go.Bar(x=["Spain"], y=[63]))

    prepared = prepare_figure_for_export(
        figure,
        chart_type="ranking",
        chart_title="Ranking comparativo",
        indicator=(
            "Felt discriminated in the 12 months before the survey in any of 8 areas of life"
        ),
        countries=["España", "Francia", "Alemania"],
        year=2024,
        source="FRA",
        filters=["Respuesta: Yes", "Edad: 25-39"],
        language="es",
    )

    layout = cast(Any, prepared).layout
    title = str(layout.title.text)

    assert (
        "Felt discriminated in the 12 months before the survey in any of 8 areas of life" in title
    )
    assert "Datos adaptados y visualizados por RainbowLens Datahub." in title.replace("<br>", " ")
    assert "Respuesta: Yes" in title
    assert "…" not in title
    assert title.count("<br>") >= 2
    assert layout.margin.t > 82


def test_exportable_graphs_share_one_client_configuration() -> None:
    config = chart_graph_config()

    assert config == {
        "displaylogo": False,
        "responsive": True,
        "modeBarButtonsToRemove": ["toImage"],
    }


def test_statistics_layout_has_one_accessible_export_action_per_graph(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.dash.pages.statistics.assert_analytics_databases_available",
        lambda: None,
    )
    monkeypatch.setattr(
        "app.dash.pages.statistics._category_options",
        lambda _year: [],
    )
    monkeypatch.setattr(
        "app.dash.pages.statistics.build_navbar",
        lambda **_kwargs: "",
    )

    layout = build_statistics_layout()
    components = list(_walk(layout))
    buttons = [
        component
        for component in components
        if getattr(component, "className", "") == "stats-chart-export-button"
    ]
    targets = {
        component.to_plotly_json()["props"]["data-chart-export-target"] for component in buttons
    }

    assert targets == {
        "stats-map-graph",
        "stats-temporal-graph",
        "stats-ranking-graph",
        "stats-average-graph",
        "stats-response-comparison-graph",
        "stats-experience-legal-radar-graph",
        "stats-response-detail-graph",
        "stats-quadrant-graph",
        "stats-median-difference-graph",
    }
    assert all(
        component.to_plotly_json()["props"]["aria-controls"]
        == component.to_plotly_json()["props"]["data-chart-export-target"]
        for component in buttons
    )
    assert all(
        component.to_plotly_json()["props"]["data-export-width"] == str(EXPORT_WIDTH)
        for component in buttons
    )


def test_client_export_reuses_rendered_plot_without_server_requests() -> None:
    script = (ROOT / "src" / "app" / "dash" / "assets" / "js" / "35_chart_export.js").read_text(
        encoding="utf-8"
    )

    assert "window.Plotly.downloadImage(graph, options)" in script
    assert "fetch(" not in script
    assert "XMLHttpRequest" not in script
    assert 'button.setAttribute("aria-busy", "true")' in script
    assert "button.disabled = false" in script
    assert "setErrorVisibility(error, true)" in script
    assert "console.error" not in script


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is unavailable")
def test_client_export_allows_two_consecutive_downloads() -> None:
    script_path = ROOT / "src" / "app" / "dash" / "assets" / "js" / "35_chart_export.js"
    harness = f"""
const fs = require("fs");
const vm = require("vm");
const calls = [];
const graph = {{
  data: [{{type: "bar", x: ["Spain"], y: [63]}}],
  layout: {{meta: {{
    export_filename: "rainbowlens-datahub_ranking_españa_2024.png",
    export_format: "png",
    export_width: 1600,
    export_height: 900,
    export_scale: 2
  }}}}
}};
const errorStatus = {{hidden: true}};
const panel = {{querySelector: () => errorStatus}};
const wrapper = {{querySelector: () => graph, matches: () => false}};
global.window = {{
  RainbowLens: {{}},
  Plotly: {{downloadImage: async (_graph, options) => calls.push(options)}},
  console
}};
global.document = {{
  addEventListener: () => {{}},
  getElementById: () => wrapper
}};
vm.runInThisContext(fs.readFileSync({json.dumps(str(script_path))}, "utf8"));
const attributes = {{}};
const button = {{
  disabled: false,
  dataset: {{chartExportTarget: "stats-ranking-graph"}},
  closest: () => panel,
  getAttribute: (name) => attributes[name] || null,
  setAttribute: (name, value) => {{attributes[name] = value;}},
  removeAttribute: (name) => {{delete attributes[name];}}
}};
(async () => {{
  await window.RainbowLens.chartExport.downloadChart(button);
  await window.RainbowLens.chartExport.downloadChart(button);
  if (calls.length !== 2) throw new Error("expected two downloads");
  if (button.disabled) throw new Error("button was not restored");
  if (calls[0].filename !== "rainbowlens-datahub_ranking_espa-a_2024") throw new Error("unsafe filename");
  if (calls[0].width !== 1600 || calls[0].height !== 900 || calls[0].scale !== 2) throw new Error("invalid resolution");
  if (!errorStatus.hidden) throw new Error("unexpected error state");
}})().catch((error) => {{console.error(error); process.exitCode = 1;}});
"""

    completed = subprocess.run(
        ["node", "-e", harness],
        capture_output=True,
        check=False,
        text=True,
        timeout=10,
    )

    assert completed.returncode == 0, completed.stderr


def test_rendered_export_metadata_tracks_visible_filters_and_country_selection() -> None:
    result = {
        "status": "ok",
        "source": "FRA",
        "year": 2024,
        "category": "Employment",
        "indicator": "Discrimination at work",
        "answer": "Yes",
        "ranking": [
            {"country": "Spain", "iso": "ES", "value": 63.0},
            {"country": "France", "iso": "FR", "value": 48.0},
        ],
        "data": [
            {
                "country": "Spain",
                "iso": "ES",
                "answer": "Yes",
                "percentage": 63.0,
                "filter_a": "Age: 25-39",
                "filter_b": "All",
            }
        ],
        "detail_data": [
            {
                "country": country,
                "iso": iso,
                "answer": answer,
                "percentage": value,
            }
            for country, iso, yes, no in (
                ("Spain", "ES", 63.0, 37.0),
                ("France", "FR", 48.0, 52.0),
            )
            for answer, value in (("Yes", yes), ("No", no))
        ],
        "history": [],
        "combined": [],
    }

    selected = _render_dashboard(result, ["ES"], "es")
    europe = _render_dashboard(result, [], "en")
    selected_meta = cast(Any, selected[2]).layout.meta
    europe_meta = cast(Any, europe[2]).layout.meta
    selected_title = cast(Any, selected[2]).layout.title.text

    assert selected_meta["export_filename"].endswith("_spain_2024.png")
    assert europe_meta["export_filename"].endswith("_europa_2024.png")
    assert "Respuesta: Yes" in selected_title
    assert "Age: 25-39" in selected_title
    assert "Fuente: FRA, EU LGBTIQ Survey III, 2023" in selected_title
    assert selected[-3] is False
    assert selected[-2] == ""
    assert selected[-1] == "stats-table-export-status is-hidden"
    with pytest.raises(ValueError, match="statistics_dashboard_requires_ready_result"):
        _render_dashboard({}, [], "en")


def _walk(component):
    yield component
    children = getattr(component, "children", None)
    if children is None:
        return
    if not isinstance(children, (list, tuple)):
        children = [children]
    for child in children:
        if hasattr(child, "children"):
            yield from _walk(child)
