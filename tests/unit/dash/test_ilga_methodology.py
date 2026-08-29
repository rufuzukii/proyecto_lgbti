from __future__ import annotations

from pathlib import Path

from dash import Dash

import app.modules.statistics.page as statistics_page
from app.shared.components.ilga_methodology import build_ilga_normalization_note


def _normalization() -> dict:
    return {
        "applied": True,
        "method": "linear_min_max",
        "original_min": -7,
        "original_max": 17,
        "target_min": 0,
        "target_max": 100,
    }


def test_methodological_note_switches_between_spanish_and_english() -> None:
    spanish = build_ilga_normalization_note(_normalization(), language="es")
    english = build_ilga_normalization_note(_normalization(), language="en")

    assert "Nota metodológica" in str(spanish)
    assert "Escala original: -7 a 17." in str(spanish)
    assert "Methodological note" in str(english)
    assert "Original scale: -7 to 17." in str(english)
    assert build_ilga_normalization_note({"applied": False}) is None


def test_statistics_no_longer_registers_ilga_selector_notes() -> None:
    app = Dash("statistics-no-ilga-selector-note", suppress_callback_exceptions=True)
    statistics_page.register_statistics_callbacks(app)
    callback_names = {
        entry["callback"].__wrapped__.__name__
        for entry in app.callback_map.values()
        if getattr(entry.get("callback"), "__wrapped__", None)
    }

    assert "update_ilga_normalization_note" not in callback_names
    assert "update_ilga_temporal_normalization_note" not in callback_names


def test_methodological_note_styles_cover_light_dark_and_mobile() -> None:
    stylesheet = Path("src/app/web/assets/ilga_methodology.css").read_text(encoding="utf-8")

    assert ".ilga-methodology-note" in stylesheet
    assert ':root[data-theme="dark"] .ilga-methodology-note' in stylesheet
    assert "@media (max-width: 640px)" in stylesheet
    assert ".stats-ilga-normalization-note" not in stylesheet
    assert ".stats-temporal-normalization-note" not in stylesheet
