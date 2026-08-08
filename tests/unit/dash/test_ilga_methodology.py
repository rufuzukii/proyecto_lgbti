from __future__ import annotations

from pathlib import Path

from dash import Dash

import app.dash.pages.statistics as statistics_page
from app.dash.components.ilga_methodology import build_ilga_normalization_note


def _callback(app: Dash, name: str):
    return next(
        value["callback"].__wrapped__
        for value in app.callback_map.values()
        if getattr(value.get("callback"), "__wrapped__", None)
        and value["callback"].__wrapped__.__name__ == name
    )


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


def test_statistics_note_disappears_for_non_normalized_year(monkeypatch) -> None:
    app = Dash("statistics-normalization-note", suppress_callback_exceptions=True)
    statistics_page.register_statistics_callbacks(app)
    callback = _callback(app, "update_ilga_normalization_note")
    monkeypatch.setattr(
        statistics_page,
        "get_ilga_document_by_year",
        lambda year: {"year": year, "normalization": _normalization()}
        if year == 2011
        else {"year": year, "normalization": {"applied": False}},
    )

    normalized, normalized_class = callback("ilga", 2011, "es")
    regular, regular_class = callback("ilga", 2013, "es")
    fra, fra_class = callback("fra", 2011, "es")

    assert normalized is not None
    assert normalized_class == "stats-ilga-normalization-note"
    assert regular is None and "is-hidden" in regular_class
    assert fra is None and "is-hidden" in fra_class


def test_temporal_evolution_discloses_normalized_years() -> None:
    app = Dash("statistics-temporal-normalization-note", suppress_callback_exceptions=True)
    statistics_page.register_statistics_callbacks(app)
    callback = _callback(app, "update_ilga_temporal_normalization_note")
    payload = {
        "source": "ILGA-Europe",
        "history": [
            {
                "year": 2011,
                "normalization_applied": True,
                "normalization_method": "linear_min_max",
                "original_scale_min": -7,
                "original_scale_max": 17,
                "target_scale_min": 0,
                "target_scale_max": 100,
            },
            {
                "year": 2012,
                "normalization_applied": True,
                "normalization_method": "linear_min_max",
                "original_scale_min": -12,
                "original_scale_max": 30,
                "target_scale_min": 0,
                "target_scale_max": 100,
            },
        ],
    }

    note, class_name = callback(payload, "en")
    hidden, hidden_class = callback({"source": "FRA"}, "en")

    assert "2011: Original scale: -7 to 17." in str(note)
    assert "2012: Original scale: -12 to 30." in str(note)
    assert class_name == "stats-temporal-normalization-note"
    assert hidden is None and "is-hidden" in hidden_class


def test_methodological_note_styles_cover_light_dark_and_mobile() -> None:
    stylesheet = Path("src/app/dash/assets/ilga_methodology.css").read_text(encoding="utf-8")

    assert ".ilga-methodology-note" in stylesheet
    assert ':root[data-theme="dark"] .ilga-methodology-note' in stylesheet
    assert "@media (max-width: 640px)" in stylesheet
    assert ".stats-ilga-normalization-note.is-hidden" in stylesheet
    assert ".stats-temporal-normalization-note.is-hidden" in stylesheet
