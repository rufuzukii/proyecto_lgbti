from app.dash.i18n import text
from app.dash.layouts.home import _ilga_copy, _ilga_country_options, _ilga_metrics


def _children(component):
    return component.to_plotly_json()["props"]["children"]


def test_text_can_render_the_requested_language_immediately() -> None:
    component = text("Mapa europeo LGBTIQ+", "European LGBTIQ+ map", language="en")

    assert _children(component) == "European LGBTIQ+ map"
    assert component.to_plotly_json()["props"]["data-i18n-es"] == "Mapa europeo LGBTIQ+"


def test_home_legal_summary_is_built_in_english_after_language_callback() -> None:
    document = {
        "year": 2026,
        "countries": [{"country": f"Country {index}", "ranking": 42.7} for index in range(49)],
    }

    copy = _ilga_copy(document, "en")
    metrics = _ilga_metrics(document, "en")
    metric_values = [
        _children(metric)[0].to_plotly_json()["props"]["children"] for metric in metrics
    ]
    metric_labels = [
        _children(metric)[1].to_plotly_json()["props"]["children"] for metric in metrics
    ]

    assert _children(copy) == "Legal information for 2026"
    assert metric_values == ["2026", "49", "42.7%"]
    assert metric_labels == ["Year", "Countries", "Legal average"]


def test_country_options_keep_codes_and_translate_visible_names() -> None:
    options = _ilga_country_options(
        {
            "countries": [
                {
                    "country": "Spain",
                    "country_code": "ES",
                }
            ]
        }
    )

    label = options[0]["label"].to_plotly_json()["props"]
    assert options[0]["value"] == "ES"
    assert label["children"] == "España (ES)"
    assert label["data-i18n-en"] == "Spain (ES)"
