from typing import Any

from app.modules.home.figures import build_fra_choropleth, build_ilga_choropleth


def _trace(figure: Any, index: int = 0) -> Any:
    return figure.data[index]


def test_home_ilga_choropleth_uses_iso3_locations() -> None:
    figure = build_ilga_choropleth(
        {
            "countries": [
                {"country": "Spain", "country_code": "ES", "ranking": 77.0},
                {"country": "Portugal", "country_code": "PT", "ranking": 68.0},
            ]
        }
    )
    trace = _trace(figure)

    assert trace.locationmode == "ISO-3"
    assert list(trace.locations) == ["ESP", "PRT"]
    assert list(trace.text) == ["España", "Portugal"]

    english = build_ilga_choropleth(
        {
            "countries": [
                {"country": "España", "country_code": "ES", "ranking": 77.0},
                {"country": "Portugal", "country_code": "PT", "ranking": 68.0},
            ]
        },
        language="en",
    )
    assert list(_trace(english).text) == ["Spain", "Portugal"]
    assert trace.customdata[0][0] == "ES"
    assert trace.colorbar.x == -0.015
    assert trace.colorbar.xanchor == "right"
    assert trace.colorbar.thickness == 10
    assert trace.colorbar.len == 0.62
    assert figure.layout.margin.l == 56
    assert figure.layout.geo.center.lon == 18
    assert figure.layout.geo.center.lat == 54
    assert figure.layout.geo.projection.scale == 1.23
    assert figure.layout.dragmode is False


def test_home_fra_choropleth_uses_iso3_locations() -> None:
    figure = build_fra_choropleth(
        {
            "answers": [
                {"country": "Spain", "country_code": "ES", "answer": "Yes", "percentage": 52.0},
                {"country": "Portugal", "country_code": "PT", "answer": "Yes", "percentage": 47.0},
                {"country": "EU27", "country_code": "EU27", "answer": "Yes", "percentage": 49.0},
            ]
        }
    )
    trace = _trace(figure)

    assert trace.locationmode == "ISO-3"
    assert list(trace.locations) == ["ESP", "PRT"]
    assert list(trace.z) == [52.0, 47.0]
    assert list(trace.text) == ["Spain", "Portugal"]
    assert trace.customdata[0][0] == "ES"
    assert trace.colorbar.x == -0.015
    assert trace.colorbar.thickness == 10
    assert figure.layout.margin.l == 56
    assert figure.layout.dragmode is False
