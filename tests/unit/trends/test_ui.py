from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from dash import Dash

import app.dash_app as dash_app_module
import app.trends.callbacks as trend_callbacks
import app.trends.layout as trend_layout
from app.dash.i18n import ui_text
from app.dash.layouts import navigation
from app.trends.analysis import analyze_historical_series
from app.trends.callbacks import register_trend_callbacks
from app.trends.charts import build_trend_figure
from app.trends.models import HistoricalPoint, SeriesMetadata, TrendAnalysis, TrendSource


def _walk(component):
    if component is None:
        return
    if isinstance(component, (list, tuple)):
        for item in component:
            yield from _walk(item)
        return
    yield component
    children = getattr(component, "children", None)
    if children is not None:
        yield from _walk(children)


def _ids(component) -> set[str]:
    return {
        item_id
        for item in _walk(component)
        if isinstance((item_id := getattr(item, "id", None)), str)
    }


def _callback(app, name: str):
    return next(
        value["callback"].__wrapped__
        for value in app.callback_map.values()
        if getattr(value.get("callback"), "__wrapped__", None)
        and value["callback"].__wrapped__.__name__ == name
    )


def _metadata() -> SeriesMetadata:
    return SeriesMetadata(
        source=TrendSource.ILGA,
        indicator_id="ranking_total",
        indicator_label="Ranking total",
        category="Ranking total",
        country_code="ES",
        country_name="España",
        unit="percentage_score",
        scale_min=0,
        scale_max=100,
        methodology="ilga_rainbow_map",
    )


def _point(year: int, value: float) -> HistoricalPoint:
    return HistoricalPoint(
        year=year,
        value=value,
        source="ilga",
        indicator_id="ranking_total",
        country_code="ES",
        country_name="España",
        unit="percentage_score",
        scale_min=0,
        scale_max=100,
        methodology="ilga_rainbow_map",
    )


def test_layout_contains_empty_lazy_controls(monkeypatch) -> None:
    monkeypatch.setattr(trend_layout, "build_navbar", lambda **_kwargs: "")
    layout = trend_layout.build_trends_layout()
    ids = _ids(layout)

    assert {
        "trend-source-select",
        "trend-category-select",
        "trend-indicator-select",
        "trend-country-select",
        "trend-year-range",
        "trend-horizon-select",
        "trend-result",
    } <= ids
    indicator = next(
        item for item in _walk(layout) if getattr(item, "id", None) == "trend-indicator-select"
    )
    assert indicator.value is None
    assert indicator.options == []
    assert "trend-history-graph" not in ids


def test_route_and_navigation_register_trends(monkeypatch) -> None:
    monkeypatch.setattr(dash_app_module, "initialize_mongo_indexes", lambda: None)
    monkeypatch.setattr(trend_layout, "build_navbar", lambda **_kwargs: "")
    app = dash_app_module.create_dash_app()
    display_page = app.callback_map["page-content.children"]["callback"].__wrapped__

    page = display_page("/tendencias", None)

    assert "trend-source-select" in _ids(page)
    assert any(
        callback.get("callback")
        and getattr(callback["callback"], "__wrapped__", None)
        and callback["callback"].__wrapped__.__name__ == "render_trend_analysis"
        for callback in app.callback_map.values()
    )

    monkeypatch.setattr(
        navigation,
        "current_user",
        SimpleNamespace(is_authenticated=False, role="anonymous", user_type=None),
    )
    navbar = navigation.build_navbar(active="trends")
    trends_link = next(
        item for item in _walk(navbar) if getattr(item, "href", None) == "/tendencias"
    )
    assert "is-active" in trends_link.className


def test_placeholders_switch_between_spanish_and_english() -> None:
    app = Dash("trend-language-test", suppress_callback_exceptions=True)
    register_trend_callbacks(app)
    callback = _callback(app, "translate_trend_placeholders")

    assert callback("es")[0] == "Selecciona una fuente"
    assert callback("en")[0] == "Select a source"
    assert ui_text("trends_not_enough", "en") == "There is not enough information."


def test_projection_horizon_uses_the_selected_historical_range(monkeypatch) -> None:
    app = Dash("trend-horizon-test", suppress_callback_exceptions=True)
    register_trend_callbacks(app)
    callback = _callback(app, "update_trend_horizon")
    all_points = [_point(year, 50 + year - 2020) for year in range(2020, 2025)]

    def filtered_points(_source, _indicator, _country, filters):
        return [
            point
            for point in all_points
            if (filters.start_year is None or point.year >= filters.start_year)
            and (filters.end_year is None or point.year <= filters.end_year)
        ]

    monkeypatch.setattr(trend_callbacks, "get_historical_series", filtered_points)

    two_year_options, two_year_value, two_year_disabled = callback(
        "ilga", "ranking", "default", "ES", [2020, 2021], "es"
    )
    four_year_options, _, _ = callback("ilga", "ranking", "default", "ES", [2020, 2023], "en")
    five_year_options, _, _ = callback("ilga", "ranking", "default", "ES", [2020, 2024], "en")

    assert [option["value"] for option in two_year_options] == [1]
    assert two_year_value == 1
    assert two_year_disabled is False
    assert [option["value"] for option in four_year_options] == [1, 2]
    assert [option["value"] for option in five_year_options] == [1, 2, 3]


def test_result_callback_handles_one_two_and_query_errors(monkeypatch) -> None:
    app = Dash("trend-result-test", suppress_callback_exceptions=True)
    register_trend_callbacks(app)
    callback = _callback(app, "render_trend_analysis")
    metadata = _metadata()

    monkeypatch.setattr(
        trend_callbacks,
        "generate_trend_analysis",
        lambda *_args, **_kwargs: (TrendAnalysis(status="insufficient"), metadata),
    )
    insufficient = callback(
        "ilga", "Ranking total", "indicator", "default", "ES", [2024, 2024], 1, "es"
    )
    assert "No hay información suficiente." in str(insufficient)
    assert "trend-history-graph" not in _ids(insufficient)

    two_year_analysis = analyze_historical_series(
        [_point(2023, 50), _point(2024, 60)], metadata, forecast_years=1
    )
    monkeypatch.setattr(
        trend_callbacks,
        "generate_trend_analysis",
        lambda *_args, **_kwargs: (two_year_analysis, metadata),
    )
    exploratory = callback(
        "ilga", "Ranking total", "indicator", "default", "ES", [2023, 2024], 1, "en"
    )
    assert "trend-history-graph" in _ids(exploratory)
    assert "exploratory" in str(exploratory).lower()
    assert "ILGA-Europe's Rainbow Map 2024" in str(exploratory)
    assert "RainbowLens Datahub" in str(exploratory)

    def fail(*_args, **_kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(trend_callbacks, "generate_trend_analysis", fail)
    error = callback("ilga", "Ranking total", "indicator", "default", "ES", [2023, 2024], 1, "en")
    assert "The temporal analysis could not be generated." in str(error)
    assert "trend-history-graph" not in _ids(error)


def test_chart_distinguishes_observed_and_forecast_in_both_languages() -> None:
    metadata = _metadata()
    analysis = analyze_historical_series(
        [_point(2022, 50), _point(2023, 60), _point(2024, 70)],
        metadata,
        forecast_years=2,
    )

    spanish = build_trend_figure(analysis, metadata, language="es")
    english = build_trend_figure(analysis, metadata, language="en")
    spanish_json = spanish.to_plotly_json()
    english_json = english.to_plotly_json()

    assert [trace["name"] for trace in spanish_json["data"]] == [
        "Datos históricos",
        "Proyección",
    ]
    assert [trace["name"] for trace in english_json["data"]] == [
        "Historical data",
        "Projection",
    ]
    assert spanish_json["data"][0]["line"].get("dash") in (None, "solid")
    assert spanish_json["data"][1]["line"]["dash"] == "dash"
    assert spanish.layout.shapes and spanish.layout.shapes[0].line.dash == "dot"
    assert spanish.layout.yaxis.range == (0, 100)


def test_trends_styles_cover_dark_mode_and_mobile() -> None:
    stylesheet = Path("src/app/dash/assets/trends.css").read_text(encoding="utf-8")

    assert ':root[data-theme="dark"] .trend-shell' in stylesheet
    assert "@media (max-width: 640px)" in stylesheet
    assert ".trend-controls" in stylesheet
    assert "grid-template-columns: 1fr" in stylesheet
    assert "overflow-x: clip" in stylesheet


def test_trends_discloses_normalized_ilga_years_in_both_languages(monkeypatch) -> None:
    app = Dash("trend-normalization-note-test", suppress_callback_exceptions=True)
    register_trend_callbacks(app)
    callback = _callback(app, "render_trend_analysis")
    metadata = _metadata()
    normalized_2011 = HistoricalPoint(
        **{
            **_point(2011, 79.17).__dict__,
            "normalization_applied": True,
            "normalization_method": "linear_min_max",
            "original_scale_min": -7,
            "original_scale_max": 17,
            "target_scale_min": 0,
            "target_scale_max": 100,
        }
    )
    analysis = analyze_historical_series(
        [normalized_2011, _point(2013, 77)],
        metadata,
        forecast_years=0,
    )
    monkeypatch.setattr(
        trend_callbacks,
        "generate_trend_analysis",
        lambda *_args, **_kwargs: (analysis, metadata),
    )

    spanish = callback(
        "ilga", "Ranking total", "indicator", "default", "ES", [2011, 2013], 0, "es"
    )
    english = callback(
        "ilga", "Ranking total", "indicator", "default", "ES", [2011, 2013], 0, "en"
    )

    assert "Nota metodológica" in str(spanish)
    assert "Escala original: -7 a 17." in str(spanish)
    assert "Methodological note" in str(english)
    assert "Original scale: -7 to 17." in str(english)


def test_production_trends_package_contains_no_fixture_data() -> None:
    package = Path("src/app/trends")
    assert not list(package.rglob("*.csv"))
    assert not list(package.rglob("*.json"))
    assert not list(package.rglob("*fixture*"))
