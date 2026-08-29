from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, cast

from dash import Dash, dcc

import app.modules.trends.callbacks as trend_callbacks
import app.modules.trends.layout as trend_layout
from app.modules.trends.callbacks import register_trend_callbacks
from app.modules.trends.charts import build_trend_figure
from app.modules.trends.forecasting_service import generate_forecast
from app.modules.trends.models import ForecastModelName, HistoricalPoint, TrendScope
from app.web.i18n import ui_text


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


def _points(count: int = 12) -> list[HistoricalPoint]:
    return [
        HistoricalPoint(
            year=2011 + index,
            value=40 + index * 2 + (index % 3),
            country_code="ES",
            country_name="Spain",
            normalization_applied=index < 2,
            normalization_method="linear_min_max" if index < 2 else "",
            original_scale_min=(-7 if index == 0 else -12 if index == 1 else None),
            original_scale_max=(17 if index == 0 else 30 if index == 1 else None),
            target_scale_min=0 if index < 2 else None,
            target_scale_max=100 if index < 2 else None,
        )
        for index in range(count)
    ]


def _result(count: int = 12):
    return generate_forecast(
        _points(count), country_code="ES", country_name="Spain", horizon=2
    )


def test_layout_only_contains_country_range_and_horizon_controls(monkeypatch) -> None:
    monkeypatch.setattr(trend_layout, "build_navbar", lambda **_kwargs: "")
    layout = trend_layout.build_trends_layout()
    ids = _ids(layout)

    assert {
        "trend-country-select",
        "trend-year-range",
        "trend-horizon-select",
        "trend-result",
        "trends-result-loading",
    } <= ids
    assert "trend-source-select" not in ids
    assert "trend-category-select" not in ids
    assert "trend-indicator-select" not in ids
    assert "trend-history-graph" not in ids


def test_initial_layout_explains_legal_score_and_not_generic_configuration(monkeypatch) -> None:
    monkeypatch.setattr(trend_layout, "build_navbar", lambda **_kwargs: "")
    rendered = str(trend_layout.build_trends_layout().to_plotly_json())

    assert "Evoluci" in rendered
    assert "ILGA-Europe Rainbow Map" in rendered
    assert "Ranking Total" not in rendered


def test_range_slider_uses_group_accessibility_label() -> None:
    field = trend_layout._field(
        "trends_historical_range",
        dcc.RangeSlider(id="test-trend-range", min=2020, max=2024),
    )
    props = field.to_plotly_json()["props"]
    label = props["children"][0]

    assert props["role"] == "group"
    assert props["aria-labelledby"] == "test-trend-range-label"
    assert label.to_plotly_json()["type"] == "Span"


def test_country_callback_uses_database_catalog_and_preserves_iso_value(monkeypatch) -> None:
    app = Dash("trend-country-test", suppress_callback_exceptions=True)
    register_trend_callbacks(app)
    callback = _callback(app, "update_trend_countries")
    monkeypatch.setattr(
        trend_callbacks,
        "get_trend_scope",
        lambda: TrendScope(countries=(("FR", "France"), ("ES", "Spain")), years=(2024,)),
    )

    options, selected, disabled, placeholder = callback("es", None)

    assert {option["value"] for option in options} == {"ES", "FR"}
    assert selected is None
    assert disabled is False
    assert placeholder == ui_text("trends_select_country", "es")


def test_country_control_loads_real_range_and_quality_based_horizons(monkeypatch) -> None:
    app = Dash("trend-controls-test", suppress_callback_exceptions=True)
    register_trend_callbacks(app)
    range_callback = _callback(app, "update_trend_range")
    horizon_callback = _callback(app, "update_trend_horizon")
    monkeypatch.setattr(
        trend_callbacks,
        "get_historical_series",
        lambda _country, _filters=None: _points(12),
    )

    minimum, maximum, value, marks, disabled = range_callback("ES")
    horizons, horizon, horizon_disabled = horizon_callback("ES", value, "en", None)

    assert (minimum, maximum, value) == (2011, 2022, [2011, 2022])
    assert set(marks) <= set(range(2011, 2023))
    assert disabled is False
    assert [option["value"] for option in horizons] == [1, 2, 3]
    assert horizon == 1
    assert horizon_disabled is False


def test_short_selected_range_limits_horizon_to_one_year(monkeypatch) -> None:
    app = Dash("trend-short-range-test", suppress_callback_exceptions=True)
    register_trend_callbacks(app)
    callback = _callback(app, "update_trend_horizon")
    monkeypatch.setattr(
        trend_callbacks,
        "get_historical_series",
        lambda _country, _filters=None: _points(4),
    )

    options, value, disabled = callback("ES", [2011, 2014], "es", 3)

    assert options == [{"label": "1 año", "value": 1}]
    assert value == 1
    assert disabled is False


def test_render_callback_returns_complete_result_and_methodology(monkeypatch) -> None:
    app = Dash("trend-render-test", suppress_callback_exceptions=True)
    register_trend_callbacks(app)
    callback = _callback(app, "render_trend_analysis")
    monkeypatch.setattr(trend_callbacks, "generate_trend_analysis", lambda *_args, **_kwargs: _result())

    rendered = callback("ES", [2011, 2022], False, 2, "es")
    ids = _ids(rendered)
    text = str(rendered.to_plotly_json())

    assert "trend-history-graph" in ids
    assert ui_text("trends_projection_method", "es") in text
    assert ui_text("trends_how_calculated", "es") in text
    assert "MAE" in text and "RMSE" in text
    assert ui_text("trends_limitations", "es") in text
    assert ui_text("trends_interpret_title", "es") in text
    assert "Qué muestra la evolución de España" in text
    assert ui_text("trends_glossary_title", "es") in text


def test_selected_method_uses_plain_and_statistical_names_for_every_model() -> None:
    expected = {
        ForecastModelName.LINEAR: ("Tendencia lineal", "Regresión lineal"),
        ForecastModelName.HOLT: (
            "Tendencia adaptada a los cambios recientes",
            "Suavizado exponencial de Holt",
        ),
        ForecastModelName.QUADRATIC: (
            "Tendencia curva",
            "Regresión polinómica de grado 2",
        ),
    }
    result = _result()
    for model, labels in expected.items():
        rendered = str(
            trend_callbacks._selected_method_explanation(
                replace(result, selected_model=model), "es"
            ).to_plotly_json()
        )
        assert labels[0] in rendered
        assert labels[1] in rendered
        assert ui_text(f"trends_method_explanation_{model.value}", "es") in rendered


def test_interpretation_and_summary_are_natural_and_localized() -> None:
    result = _result()
    spanish = str(trend_callbacks._interpretation_guide(result, "es").to_plotly_json())
    english = str(trend_callbacks._interpretation_guide(result, "en").to_plotly_json())
    summary = str(trend_callbacks._evolution_summary(result, "es").to_plotly_json())

    assert "parte inferior" in spanish
    assert "escala" in spanish and "0 a 100" in spanish
    assert "not an official prediction" in english
    assert "España" in summary
    assert "Entre 2011 y 2022" in summary


def test_insufficient_data_keeps_history_but_never_draws_fake_projection(monkeypatch) -> None:
    result = generate_forecast(
        _points(2), country_code="ES", country_name="Spain", horizon=3
    )
    rendered = trend_callbacks._render_result(result, "en")
    graph = next(item for item in _walk(rendered) if getattr(item, "id", None) == "trend-history-graph")

    assert result.status == "insufficient"
    assert len(graph.figure.data) == 1
    assert ui_text("trends_not_enough_projection", "en") in str(rendered.to_plotly_json())


def test_short_valid_series_displays_exploratory_warning() -> None:
    result = generate_forecast(
        _points(4), country_code="ES", country_name="Spain", horizon=3
    )
    rendered = trend_callbacks._render_result(result, "es")

    assert result.exploratory is True
    assert ui_text("trends_exploratory_warning", "es") in str(rendered.to_plotly_json())


def test_chart_distinguishes_history_forecast_uncertainty_and_missing_years() -> None:
    points = _points(10)
    del points[5]
    result = generate_forecast(points, country_code="ES", country_name="Spain", horizon=2)

    figure = build_trend_figure(result, language="en")

    figure_data = cast(Any, figure.data)
    assert len(figure_data) == 3
    historical = figure_data[0]
    forecast = figure_data[2]
    assert historical.connectgaps is False
    assert None in historical.y
    assert forecast.line.dash == "dash"
    assert figure.layout.yaxis.range == (0, 100)
    assert "RainbowLens DataHub" in str(forecast.hovertext)
    assert "Type: RainbowLens DataHub projection" in str(forecast.hovertext)
    assert figure.layout.yaxis.ticksuffix is None


def test_normalization_note_is_rendered_for_2011_and_2012() -> None:
    rendered = trend_callbacks._render_result(_result(), "es")
    notes = [item for item in _walk(rendered) if "trend-normalization-note" in str(getattr(item, "className", ""))]

    assert notes
    text = str(notes[0].to_plotly_json())
    assert "2011" in text and "2012" in text


def test_loading_message_and_new_methodology_are_translated() -> None:
    assert ui_text("loading_trends", "es") == "Calculando tendencia..."
    assert ui_text("loading_trends", "en") == "Calculating trend..."
    assert ui_text("trends_how_calculated", "en") == "View detailed methodology"
    assert "official" in ui_text("trends_limitations_detail", "en")


def test_css_supports_dark_mode_responsive_cards_and_local_table_scroll() -> None:
    css = Path("src/app/web/assets/trends.css").read_text(encoding="utf-8")

    assert '[data-theme="dark"] .trend-method-details summary' in css
    assert ".trend-table-scroll" in css and "overflow-x: auto" in css
    assert "@media (max-width: 640px)" in css
    assert ".trend-controls" in css and "grid-template-columns: 1fr" in css
    assert ".trend-explanation-grid" in css
    assert ".trend-glossary-list" in css
    assert ".trend-selected-method" in css
