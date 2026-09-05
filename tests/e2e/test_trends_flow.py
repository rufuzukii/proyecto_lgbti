from __future__ import annotations

from dash import Dash

import app.modules.trends.callbacks as trend_callbacks
from app.modules.trends.callbacks import register_trend_callbacks
from app.modules.trends.forecasting_service import generate_forecast
from app.modules.trends.models import HistoricalPoint, TrendScope


def _callback(app: Dash, name: str):
    return next(
        value["callback"].__wrapped__
        for value in app.callback_map.values()
        if getattr(value.get("callback"), "__wrapped__", None)
        and value["callback"].__wrapped__.__name__ == name
    )


def _points(country: str, offset: float = 0.0) -> list[HistoricalPoint]:
    return [
        HistoricalPoint(
            year=2011 + index,
            value=45 + offset + index * 1.2 + (index % 3),
            country_code=country,
            country_name="Spain" if country == "ES" else "France",
        )
        for index in range(13)
    ]


def test_country_horizon_and_language_round_trip_updates_entire_methodology(monkeypatch) -> None:
    app = Dash("trends-flow-e2e", suppress_callback_exceptions=True)
    register_trend_callbacks(app)
    countries_callback = _callback(app, "update_trend_countries")
    range_callback = _callback(app, "update_trend_range")
    horizon_callback = _callback(app, "update_trend_horizon")
    analysis_callback = _callback(app, "render_trend_analysis")
    datasets = {"ES": _points("ES"), "FR": _points("FR", 4)}
    monkeypatch.setattr(
        trend_callbacks,
        "get_trend_scope",
        lambda: TrendScope(
            countries=(("ES", "Spain"), ("FR", "France")), years=tuple(range(2011, 2024))
        ),
    )
    monkeypatch.setattr(
        trend_callbacks,
        "get_historical_series",
        lambda code, _filters=None: datasets[code],
    )
    monkeypatch.setattr(
        trend_callbacks,
        "generate_trend_analysis",
        lambda code, _filters, forecast_years: generate_forecast(
            datasets[code],
            country_code=code,
            country_name="Spain" if code == "ES" else "France",
            horizon=forecast_years,
        ),
    )

    options, initial_country, *_ = countries_callback("es", None)
    country = "ES"
    selected_range = range_callback(country)[2]
    horizon = horizon_callback(country, selected_range, "es", 1)[1]
    spanish = analysis_callback(country, selected_range, False, horizon, "es")
    longer = analysis_callback(country, selected_range, False, 3, "es")
    french = analysis_callback("FR", selected_range, False, 2, "en")

    assert {option["value"] for option in options} == {"ES", "FR"}
    assert initial_country is None
    assert "Ver metodología detallada" in str(spanish.to_plotly_json())
    assert "3 años" in str(longer.to_plotly_json())
    assert "View detailed methodology" in str(french.to_plotly_json())
    assert "France" in str(french.to_plotly_json())
