from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
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
        "rainbow-lens_ranking-comparativo_discriminacion-en-el-empleo-promocion_"
        "espana-franca_2024.png"
    )
    assert malicious.endswith(".png")
    assert ".." not in malicious
    assert "<" not in malicious
    assert "/" not in malicious
    assert len(malicious) <= EXPORT_FILENAME_MAX_LENGTH


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
    assert layout.meta["export_filename"].endswith(
        "_espana-francia_2024.png"
    )
    assert "Discriminación en el empleo" in layout.title.text
    assert "Fuente: FRA EU LGBTIQ Survey III" in layout.title.text
    assert "Respuesta: Yes" in layout.title.text
    assert layout.margin.t >= 82


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
        "app.dash.pages.statistics._year_options",
        lambda _source: [],
    )
    monkeypatch.setattr(
        "app.dash.pages.statistics._category_options",
        lambda _source, _year: [],
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
        component.to_plotly_json()["props"]["data-chart-export-target"]
        for component in buttons
    }

    assert targets == {
        "stats-map-graph",
        "stats-temporal-graph",
        "stats-ranking-graph",
        "stats-distribution-graph",
        "stats-average-graph",
        "stats-country-comparison-graph",
        "stats-radar-graph",
        "stats-response-detail-graph",
        "stats-gap-graph",
        "stats-scatter-graph",
        "stats-combined-heatmap",
    }
    assert all(
        component.to_plotly_json()["props"]["aria-controls"]
        == component.to_plotly_json()["props"]["data-chart-export-target"]
        for component in buttons
    )
    assert all(
        component.to_plotly_json()["props"]["data-export-width"]
        == str(EXPORT_WIDTH)
        for component in buttons
    )


def test_client_export_reuses_rendered_plot_without_server_requests() -> None:
    script = (
        ROOT / "src" / "app" / "dash" / "assets" / "js" / "35_chart_export.js"
    ).read_text(encoding="utf-8")

    assert "window.Plotly.downloadImage(graph, options)" in script
    assert "fetch(" not in script
    assert "XMLHttpRequest" not in script
    assert 'button.setAttribute("aria-busy", "true")' in script
    assert "button.disabled = false" in script
    assert "statistics_chart_export_failed" in script


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is unavailable")
def test_client_export_allows_two_consecutive_downloads() -> None:
    script_path = (
        ROOT / "src" / "app" / "dash" / "assets" / "js" / "35_chart_export.js"
    )
    harness = f"""
const fs = require("fs");
const vm = require("vm");
const calls = [];
const graph = {{
  data: [{{type: "bar", x: ["Spain"], y: [63]}}],
  layout: {{meta: {{
    export_filename: "rainbow-lens_ranking_españa_2024.png",
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
  if (calls[0].filename !== "rainbow-lens_ranking_espa-a_2024") throw new Error("unsafe filename");
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
    assert "Fuente: FRA EU LGBTIQ Survey III" in selected_title


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
