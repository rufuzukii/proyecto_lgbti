from __future__ import annotations

from typing import Any, cast

import plotly.graph_objects as go

from app.analytics.figures import build_ilga_choropleth
from app.analytics.legal_ranking import (
    LEGAL_MAP_EXPORT_HEIGHT,
    LEGAL_MAP_EXPORT_SCALE,
    LEGAL_MAP_EXPORT_WIDTH,
    build_legal_map_export_figure,
    build_legal_ranking,
    export_legal_map_png,
    legal_map_export_filename,
    legal_ranking_payload,
)
from app.dash.i18n import country_labels


def _document() -> dict:
    return {
        "year": 2026,
        "countries": [
            {"country_code": "ES", "country": "Spain", "ranking": 78},
            {"country_code": "BE", "country": "Belgium", "ranking": 85},
            {"country_code": "AT", "country": "Austria", "ranking": 85.0},
            {"country_code": "MT", "country": "Malta", "ranking": 0},
            {"country_code": "FR", "country": "France", "ranking": None},
        ],
    }


def test_legal_ranking_is_descending_stable_and_keeps_zero() -> None:
    ranking = build_legal_ranking(_document())

    assert [(entry.country_code, entry.score) for entry in ranking] == [
        ("AT", 85.0),
        ("BE", 85.0),
        ("ES", 78.0),
        ("MT", 0.0),
    ]
    assert ranking[-1].score_text == "0%"
    assert all(entry.country_code != "FR" for entry in ranking)


def test_legal_ranking_uses_the_central_country_catalog_in_both_languages() -> None:
    spanish = build_legal_ranking(
        _document(),
        country_name_resolver=lambda code, fallback: country_labels(code, fallback)[0],
    )
    english = build_legal_ranking(
        _document(),
        country_name_resolver=lambda code, fallback: country_labels(code, fallback)[1],
    )

    assert next(entry.country_name for entry in spanish if entry.country_code == "ES") == "España"
    assert next(entry.country_name for entry in english if entry.country_code == "ES") == "Spain"
    assert next(entry.country_name for entry in spanish if entry.country_code == "BE") == "Bélgica"
    assert next(entry.country_name for entry in english if entry.country_code == "BE") == "Belgium"


def test_combined_export_figure_contains_map_legend_ranking_and_attribution() -> None:
    document = _document()
    ranking = build_legal_ranking(document)
    map_figure = build_ilga_choropleth(document, language="en")

    figure = build_legal_map_export_figure(
        map_figure,
        legal_ranking_payload(ranking),
        year=2026,
        language="en",
    )

    traces = cast(Any, figure).data
    assert [trace.type for trace in traces] == ["choropleth", "table"]
    assert traces[0].colorbar.x == 0.015
    assert list(traces[1].cells.values[1]) == [
        "Austria",
        "Belgium",
        "Spain",
        "Malta",
    ]
    assert list(traces[1].cells.values[2])[-1] == "0%"
    assert "RainbowLens DataHub" in figure.layout.title.text
    assert "European LGBTIQ+ map" in figure.layout.title.text
    annotation_text = " ".join(str(annotation.text) for annotation in figure.layout.annotations)
    assert "Legal ranking · 2026" in annotation_text
    assert "ILGA-Europe's Rainbow Map 2026" in annotation_text
    assert "RainbowLens Datahub" in annotation_text


def test_png_export_uses_kaleido_dimensions_and_descriptive_filename(monkeypatch) -> None:
    calls: list[dict] = []

    def fake_to_image(_figure: go.Figure, **kwargs):
        calls.append(kwargs)
        return b"\x89PNG\r\n\x1a\nimage"

    monkeypatch.setattr("app.analytics.legal_ranking.pio.to_image", fake_to_image)

    payload = export_legal_map_png(go.Figure())

    assert payload.startswith(b"\x89PNG")
    assert calls == [
        {
            "format": "png",
            "width": LEGAL_MAP_EXPORT_WIDTH,
            "height": LEGAL_MAP_EXPORT_HEIGHT,
            "scale": LEGAL_MAP_EXPORT_SCALE,
            "validate": True,
        }
    ]
    assert legal_map_export_filename(2026) == "rainbowlens_ranking_legal_europa_2026.png"


def test_combined_export_uses_a_complete_dark_palette_when_requested() -> None:
    document = _document()
    ranking = build_legal_ranking(document)

    figure = build_legal_map_export_figure(
        build_ilga_choropleth(document),
        legal_ranking_payload(ranking),
        year=2026,
        language="es",
        theme="dark",
    )
    traces = cast(Any, figure).data

    assert figure.layout.paper_bgcolor == "#111827"
    assert figure.layout.plot_bgcolor == "#111827"
    assert figure.layout.font.color == "#f7f9fc"
    assert figure.layout.geo.bgcolor == "#111827"
    assert figure.layout.geo.landcolor == "#1a2232"
    assert traces[1].header.fill.color == "#203342"
    assert traces[1].cells.fill.color == "#111827"
    assert traces[1].cells.font.color == "#f7f9fc"
