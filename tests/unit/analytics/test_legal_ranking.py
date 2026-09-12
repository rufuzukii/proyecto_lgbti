from __future__ import annotations

import socket
import subprocess
from io import BytesIO
from typing import Any, cast

import plotly.graph_objects as go
import pytest
from PIL import Image, ImageDraw

from app.modules.home.figures import build_ilga_choropleth
from app.shared.data.geography import ISO2_TO_ISO3
from app.shared.data.legal_ranking import (
    LEGAL_MAP_EXPORT_HEIGHT,
    LEGAL_MAP_EXPORT_SCALE,
    LEGAL_MAP_EXPORT_WIDTH,
    LegalMapExportError,
    build_legal_map_export_figure,
    build_legal_ranking,
    export_legal_map_png,
    legal_map_export_filename,
    legal_ranking_payload,
)
from app.web.i18n import country_labels


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


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("language", ["es", "en"])
def test_png_export_renders_map_ranking_and_source_without_a_browser(
    monkeypatch, theme: str, language: str
) -> None:
    drawn_text: list[str] = []
    original_text = ImageDraw.ImageDraw.text

    def capture_text(self, xy, text, *args, **kwargs):
        drawn_text.append(text)
        return original_text(self, xy, text, *args, **kwargs)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Image export must not start processes or connect to the network")

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", capture_text)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    document = _document()
    figure = build_legal_map_export_figure(
        build_ilga_choropleth(document, language=language),
        legal_ranking_payload(build_legal_ranking(document)),
        year=2026,
        language=language,
        theme=theme,
    )
    original_figure = figure.to_json()
    payload = export_legal_map_png(figure)

    with Image.open(BytesIO(payload)) as image:
        assert image.format == "PNG"
        assert image.size == (
            int(LEGAL_MAP_EXPORT_WIDTH * LEGAL_MAP_EXPORT_SCALE),
            int(LEGAL_MAP_EXPORT_HEIGHT * LEGAL_MAP_EXPORT_SCALE),
        )
        assert image.getpixel((0, 0)) == ((17, 24, 39) if theme == "dark" else (255, 255, 255))
        # El mapa incluye colores de los datos y países sin datos; la tabla también se dibuja.
        map_colors = image.crop((180, 225, 1800, 1620)).getcolors(5_000_000)
        table_colors = image.crop((1950, 225, 2600, 420)).getcolors(5_000_000)
        assert map_colors is not None and len(map_colors) > 4
        assert table_colors is not None and len(table_colors) > 4
    assert "RainbowLens DataHub" in drawn_text
    assert ("Legal ranking · 2026" if language == "en" else "Ranking legal · 2026") in drawn_text
    assert ("No data" if language == "en" else "Sin datos") in drawn_text
    assert any("ILGA-Europe" in text for text in drawn_text)
    assert [text for text in drawn_text if text in {"Austria", "Belgium", "Spain", "Malta"}] == [
        "Austria",
        "Belgium",
        "Spain",
        "Malta",
    ]
    assert "0%" in drawn_text
    assert figure.to_json() == original_figure
    assert legal_map_export_filename(2026) == "rainbowlens_ranking_legal_europa_2026.png"


def test_png_export_keeps_every_country_in_a_full_ranking(monkeypatch) -> None:
    drawn_text: list[str] = []
    original_text = ImageDraw.ImageDraw.text

    def capture_text(self, xy, text, *args, **kwargs):
        drawn_text.append(text)
        return original_text(self, xy, text, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", capture_text)
    document = {
        "countries": [
            {"country_code": code, "country": country_labels(code, code)[1], "ranking": index * 2}
            for index, code in enumerate(ISO2_TO_ISO3)
        ]
    }
    ranking = build_legal_ranking(document)
    figure = build_legal_map_export_figure(
        build_ilga_choropleth(document), legal_ranking_payload(ranking), year=2026, language="en"
    )
    payload = export_legal_map_png(figure)
    assert payload.startswith(b"\x89PNG")
    for entry in ranking:
        assert entry.country_name in drawn_text
    assert str(len(ranking)) in drawn_text


def test_png_export_distinguishes_zero_maximum_and_missing_country_values() -> None:
    document = {
        "countries": [
            {"country_code": "ES", "country": "Spain", "ranking": 0},
            {"country_code": "FR", "country": "France", "ranking": 100},
            {"country_code": "DE", "country": "Germany", "ranking": None},
        ]
    }
    figure = build_legal_map_export_figure(
        build_ilga_choropleth(document),
        legal_ranking_payload(build_legal_ranking(document)),
        year=2026,
        language="en",
    )
    with Image.open(BytesIO(export_legal_map_png(figure))) as image:
        pixels = image.getcolors(5_000_000)
        assert pixels is not None
        colors = {color: count for count, color in pixels}
    # Miles de píxeles del mapa: no basta con que el color aparezca en la leyenda.
    assert colors[(215, 48, 39)] > 1000
    assert colors[(23, 114, 69)] > 1000
    assert colors[(237, 241, 244)] > 1000


def test_png_export_handles_an_empty_legal_map() -> None:
    figure = build_legal_map_export_figure(go.Figure(), [], year=None, language="es")
    with Image.open(BytesIO(export_legal_map_png(figure))) as image:
        image.verify()


def test_png_export_preserves_its_public_error_contract(monkeypatch) -> None:
    def fail(*_args, **_kwargs):
        raise OSError("Cannot allocate the image")

    monkeypatch.setattr("app.shared.data.legal_map_image.render_legal_map_png", fail)
    with pytest.raises(LegalMapExportError) as error:
        export_legal_map_png(go.Figure())
    assert isinstance(error.value.__cause__, OSError)


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
