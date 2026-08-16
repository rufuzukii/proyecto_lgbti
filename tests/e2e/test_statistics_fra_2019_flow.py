from __future__ import annotations

from dash import Dash

from app.dash.pages import statistics as statistics_page


def _callback(app: Dash, name: str):
    return next(
        value["callback"].__wrapped__
        for value in app.callback_map.values()
        if getattr(value.get("callback"), "__wrapped__", None)
        and value["callback"].__wrapped__.__name__ == name
    )


def test_survey_ii_uses_its_catalog_and_hides_nonexistent_segmentations(monkeypatch) -> None:
    app = Dash("statistics-fra-2019-e2e", suppress_callback_exceptions=True)
    statistics_page.register_statistics_callbacks(app)
    categories = _callback(app, "update_categories_for_survey")
    indicators = _callback(app, "update_fra_indicators")
    controls = _callback(app, "update_fra_controls")
    monkeypatch.setattr(
        statistics_page,
        "ctx",
        type("Context", (), {"triggered_id": "stats-survey-select"})(),
    )
    monkeypatch.setattr(
        statistics_page,
        "_category_options",
        lambda year, _language: (
            [{"label": "Discrimination", "value": "Discrimination"}]
            if year == 2019
            else []
        ),
    )
    monkeypatch.setattr(
        statistics_page,
        "get_fra_mongo_indicators_by_category",
        lambda category, year: [
            type(
                "Indicator",
                (),
                {"code": "DEX1", "question": "Survey II question"},
            )()
        ]
        if (category, year) == ("Discrimination", 2019)
        else [],
    )
    monkeypatch.setattr(
        statistics_page,
        "get_fra_control_payload",
        lambda code, category, year: {
            "answers": [{"label": "Yes", "value": "Yes"}],
            "default_answer": "Yes",
            "segmentations": [{"label": "All", "value": "All"}],
            "values": {"All": [{"label": "All", "value": "All"}]},
            "response_type": "standard",
        },
    )

    category_result = categories("fra_survey_ii", "es", None)
    indicator_result = indicators("fra_survey_ii", "Discrimination")
    control_result = controls("DEX1", "es", "Discrimination", "fra_survey_ii")

    assert category_result[2]["year"] == 2019
    assert category_result[0][0]["value"] == "Discrimination"
    assert indicator_result[0][0]["value"] == "DEX1"
    assert control_result[1] == "Yes"
    assert control_result[3] == "All"
    assert control_result[7].endswith("is-hidden")
