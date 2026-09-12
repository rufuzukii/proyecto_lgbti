import pytest

from app.modules.statistics.figures import (
    build_comparative_ranking_chart,
    build_eu_average_comparison_chart,
)


@pytest.mark.parametrize(
    "language, names",
    [("es", {"España", "Alemania", "Francia"}), ("en", {"Spain", "Germany", "France"})],
)
@pytest.mark.parametrize(
    "builder", [build_comparative_ranking_chart, build_eu_average_comparison_chart]
)
def test_country_labels_are_localized_without_changing_values(builder, language, names):
    rows = [
        {"iso": "ES", "country": "Spain", "value": 0},
        {"iso": "DE", "country": "Germany", "value": 50},
        {"iso": "FR", "country": "France", "value": None},
    ]
    figure = builder(rows, ["ES", "DE", "FR"], language)
    assert set(figure.data[0].y) == names
    values = dict(zip(figure.data[0].y, figure.data[0].x, strict=True))
    assert values["España" if language == "es" else "Spain"] == 0
    assert values["Francia" if language == "es" else "France"] is None
    assert rows[0]["country"] == "Spain"
