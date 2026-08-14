from __future__ import annotations

from typing import Any, cast

from app.trends import historical_series
from app.trends.charts import build_trend_figure
from app.trends.forecasting_service import generate_forecast


def test_ilga_rows_to_forecast_result_and_figure(monkeypatch) -> None:
    rows = [
        {
            "year": year,
            "country": "Spain",
            "iso": "ES",
            "value": 50 + index * 1.5 + (index % 2),
            "source": "ILGA-Europe",
            "normalization_applied": year in {2011, 2012},
            "normalization_method": "linear_min_max" if year in {2011, 2012} else "",
            "original_scale_min": -7 if year == 2011 else -12 if year == 2012 else None,
            "original_scale_max": 17 if year == 2011 else 30 if year == 2012 else None,
            "target_scale_min": 0 if year in {2011, 2012} else None,
            "target_scale_max": 100 if year in {2011, 2012} else None,
        }
        for index, year in enumerate(range(2011, 2024))
    ]
    monkeypatch.setattr(historical_series, "get_ilga_history_rows", lambda *_args: rows)

    points = historical_series.load_ilga_global_history()
    result = generate_forecast(
        points, country_code="ES", country_name="Spain", horizon=3
    )
    figure = build_trend_figure(result, language="es")

    assert result.status == "ok"
    assert len(result.historical) == 13
    assert result.normalization_years == (2011, 2012)
    assert len(result.validation) == 3
    assert len(result.forecast) == 3
    assert all(0 <= point.value <= 100 for point in result.forecast)
    assert len(cast(Any, figure.data)) == 3
    assert figure.layout.yaxis.range == (0, 100)
