from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from dash import Dash

from app.modules.home import page as home
from app.shared.data.legal_ranking import (
    LEGAL_MAP_EXPORT_HEIGHT,
    LEGAL_MAP_EXPORT_SCALE,
    LEGAL_MAP_EXPORT_WIDTH,
)


def _walk(component: Any):
    if component is None:
        return
    if isinstance(component, (list, tuple)):
        for child in component:
            yield from _walk(child)
        return
    yield component
    yield from _walk(getattr(component, "children", None))


def _callback(app: Dash, name: str):
    return next(
        entry["callback"].__wrapped__
        for entry in app.callback_map.values()
        if getattr(entry.get("callback"), "__wrapped__", None)
        and entry["callback"].__wrapped__.__name__ == name
    )


def _document() -> dict[str, Any]:
    return {
        "year": 2026,
        "countries": [
            {"country_code": "ES", "country": "Spain", "ranking": 78},
            {"country_code": "MT", "country": "Malta", "ranking": 89},
            {"country_code": "DE", "country": "Germany", "ranking": 67.5},
        ],
    }


def _app(monkeypatch) -> Dash:
    monkeypatch.setattr(home, "build_navbar", lambda **_kwargs: "")
    monkeypatch.setattr(home, "current_user", SimpleNamespace(is_authenticated=False))
    monkeypatch.setattr(home, "get_latest_ilga_document", _document)
    monkeypatch.setattr(home, "get_ilga_years", lambda: [2026])
    app = Dash("home-ranking-test", suppress_callback_exceptions=True)
    app.layout = home.build_home_layout()
    home.register_home_callbacks(app)
    return app


def test_home_places_one_accessible_ranking_beside_the_existing_map(monkeypatch) -> None:
    app = _app(monkeypatch)
    components = {
        component.id: component
        for component in _walk(app.layout)
        if isinstance(getattr(component, "id", None), str)
    }

    ranking = components["home-legal-ranking"]
    ranking_rows = [
        component
        for component in _walk(ranking)
        if getattr(component, "className", None) == "home-legal-ranking-row"
    ]

    assert len(ranking_rows) == 3
    assert "Malta" in str(ranking_rows[0])
    assert "89%" in str(ranking_rows[0])
    assert "Alemania" in str(ranking_rows[-1])
    export_props = components["home-map-export-button"].to_plotly_json()["props"]
    error_props = components["home-map-export-status"].to_plotly_json()["props"]
    assert export_props["aria-label"] == "Descargar imagen del mapa y ranking legal"
    assert export_props["data-i18n-aria-label-en"] == "Download legal map and ranking image"
    assert export_props["data-i18n-title-en"] == "Download image"
    assert export_props["data-chart-export"] == "true"
    assert export_props["data-chart-export-target"] == "home-map-graph"
    assert export_props["aria-controls"] == "home-map-graph"
    assert error_props["data-chart-export-error"] == "home-map-graph"
    assert error_props["hidden"] is True
    assert components["home-map-graph"].figure.data
    assert (
        components["home-map-graph"].figure.layout.meta["export_filename"]
        == "rainbowlens_mapa_legal_europa_2026"
    )
    export_meta = components["home-map-graph"].figure.layout.meta
    assert [row["country_code"] for row in export_meta["export_map_ranking"]] == [
        "MT",
        "ES",
        "DE",
    ]
    assert export_meta["export_ranking_title"] == "Ranking legal · 2026"
    assert export_meta["export_width"] == LEGAL_MAP_EXPORT_WIDTH
    assert export_meta["export_height"] == LEGAL_MAP_EXPORT_HEIGHT
    assert export_meta["export_scale"] == LEGAL_MAP_EXPORT_SCALE
    assert "toImage" in components["home-map-graph"].config["modeBarButtonsToRemove"]


def test_map_and_ranking_share_one_document_query_and_translate_together(monkeypatch) -> None:
    app = _app(monkeypatch)
    calls: list[int | None] = []
    monkeypatch.setattr(
        home,
        "get_ilga_document_by_year",
        lambda year: calls.append(year) or _document(),
    )
    callback = _callback(app, "update_home_map")

    result = callback(2026, "en")

    assert calls == [2026]
    assert "Legal ranking · 2026" in str(result[5])
    assert [row["country_name"] for row in result[6]] == ["Malta", "Spain", "Germany"]
    assert len(calls) == 1


def test_home_map_export_reuses_the_rendered_plot_without_a_server_callback(monkeypatch) -> None:
    app = _app(monkeypatch)
    callback_names = {
        entry["callback"].__wrapped__.__name__
        for entry in app.callback_map.values()
        if getattr(entry.get("callback"), "__wrapped__", None)
    }
    script = Path("src/app/web/assets/js/35_chart_export.js").read_text(encoding="utf-8")

    assert "download_home_legal_map" not in callback_names
    assert "window.Plotly.downloadImage(graph, options)" in script
    assert "button.parentElement" in script
    assert "data-chart-export-error" in script


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is unavailable")
@pytest.mark.parametrize(
    ("width", "height", "ranking_title"),
    (
        (LEGAL_MAP_EXPORT_WIDTH, LEGAL_MAP_EXPORT_HEIGHT, "Ranking legal · 2026"),
        (1600, 900, "Ranking de países"),
        (1600, 900, "Country ranking"),
    ),
)
def test_map_download_places_the_ranking_title_above_its_table(
    width: int, height: int, ranking_title: str
) -> None:
    script_path = Path("src/app/web/assets/js/35_chart_export.js").resolve()
    harness = f"""
const fs = require("fs");
const vm = require("vm");
const captured = {{}};
const graph = {{
  data: [{{type: "choropleth", locations: ["ES", "MT"], z: [78, 89]}}],
  layout: {{
    geo: {{}},
    meta: {{
      export_filename: "rainbowlens_mapa_legal_europa_2026",
      export_width: {width},
      export_height: {height},
      export_scale: {LEGAL_MAP_EXPORT_SCALE},
      export_map_title: "Mapa europeo LGBTIQ+",
      export_ranking_title: {json.dumps(ranking_title)},
      export_country_label: "País",
      export_score_label: "Puntuación legal",
      export_map_ranking: [
        {{country_code: "MT", country_name: "Malta", score: 89}},
        {{country_code: "ES", country_name: "España", score: 78}}
      ]
    }}
  }}
}};
const exportGraph = {{style: {{}}, setAttribute: () => {{}}, remove: () => {{}}}};
global.window = {{
  RainbowLens: {{
    state: {{currentTheme: () => "light"}},
    theme: {{colorsForTheme: () => ({{
      paper: "#ffffff", plot: "#ffffff", font: "#252a31", axis: "#252a31",
      grid: "#e5e9eb", muted: "#475569", legend: "#ffffff",
      geoBg: "#ffffff", geoLand: "#edf1f4", geoOcean: "#dcebf2", geoCoast: "#b9c0ca",
      mapbox: "open-street-map"
    }})}}
  }},
  Plotly: {{
    newPlot: async (_target, data, layout) => {{captured.data = data; captured.layout = layout;}},
    downloadImage: async (_target, options) => {{captured.options = options;}},
    purge: () => {{}}
  }}
}};
global.document = {{
  addEventListener: () => {{}},
  documentElement: {{dataset: {{theme: "light"}}}},
  getElementById: () => ({{querySelector: () => graph, matches: () => false}}),
  createElement: () => exportGraph,
  body: {{insertAdjacentElement: () => {{}}}}
}};
vm.runInThisContext(fs.readFileSync({json.dumps(str(script_path))}, "utf8"));
const attributes = {{}};
const button = {{
  disabled: false,
  dataset: {{chartExportTarget: "home-map-graph"}},
  parentElement: {{querySelector: () => ({{hidden: true}})}},
  closest: () => null,
  getAttribute: (name) => attributes[name] || null,
  setAttribute: (name, value) => {{attributes[name] = value;}},
  removeAttribute: (name) => {{delete attributes[name];}}
}};
(async () => {{
  await window.RainbowLens.chartExport.downloadChart(button);
  const table = captured.data.find((trace) => trace.type === "table");
  if (!table) throw new Error("legal ranking table missing from export");
  if (table.cells.values[1].join(",") !== "Malta,España") throw new Error("ranking rows missing");
  if (!captured.layout.annotations.some((item) => item.text.includes({json.dumps(ranking_title)}))) {{
    throw new Error("ranking title missing");
  }}
  const heading = captured.layout.annotations.find((item) => item.text.includes({json.dumps(ranking_title)}));
  if (heading.yanchor !== "bottom" || heading.y < table.domain.y[1] || heading.yshift < 8) {{
    throw new Error("ranking heading overlaps the table header");
  }}
  if (captured.layout.geo.domain.x[1] !== 0.7) throw new Error("map was not resized");
  if (captured.options.width !== {width}
      || captured.options.height !== {height}) throw new Error("export size mismatch");
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


def test_home_ranking_css_is_dark_mode_safe_and_stacks_below_the_map() -> None:
    css = Path("src/app/web/assets/home.css").read_text(encoding="utf-8")

    assert "grid-template-columns: minmax(0, 3.3fr) minmax(210px, 0.72fr);" in css
    assert "@media (max-width: 1050px)" in css
    assert ".home-map-visual-grid {\n    grid-template-columns: minmax(0, 1fr);" in css
    assert 'body[data-theme="dark"] .home-legal-ranking' in css
    assert ".home-legal-ranking-list" in css
    assert "overflow-y: auto;" in css
