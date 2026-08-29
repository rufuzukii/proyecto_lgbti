from __future__ import annotations

from dash import Dash

from app.modules.statistics import page as statistics_page


def _callback(app: Dash, name: str):
    return next(
        value["callback"].__wrapped__
        for value in app.callback_map.values()
        if getattr(value.get("callback"), "__wrapped__", None)
        and value["callback"].__wrapped__.__name__ == name
    )


def test_survey_ii_keeps_nonexistent_segmentations_visible_and_disabled(monkeypatch) -> None:
    app = Dash("statistics-fra-2019-e2e", suppress_callback_exceptions=True)
    statistics_page.register_statistics_callbacks(app)
    categories = _callback(app, "update_categories_for_survey")
    indicators = _callback(app, "update_fra_indicators")
    controls = _callback(app, "update_fra_controls")
    placeholders = _callback(app, "translate_statistics_controls")
    demographic_values = _callback(app, "update_demographic_values")
    identity_state = _callback(app, "update_identity_filter_state")
    identity_values = _callback(app, "update_identity_values")
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

    assert placeholders("es", None)[1] == "Selecciona primero una categoría"
    assert placeholders("es", "Discrimination")[1] == "Selecciona un indicador"
    assert category_result[2]["year"] == 2019
    assert category_result[0][0]["value"] == "Discrimination"
    assert indicator_result[0][0]["value"] == "DEX1"
    assert control_result[1] == "Yes"
    assert control_result[3] == "All"
    assert all(option["disabled"] for option in control_result[2])
    assert "is-hidden" not in control_result[7]
    assert "is-disabled" in control_result[7]
    assert control_result[8] is False
    assert "is-disabled" in control_result[9]

    payload = control_result[4]
    demographic_value_options, demographic_value = demographic_values("All", payload, None)
    identity_options, identity_type, identity_class = identity_state(
        "All", payload, "es", None
    )
    identity_value_options, identity_value = identity_values("All", payload, "All", None)

    assert demographic_value == "All"
    assert all(option["disabled"] for option in demographic_value_options)
    assert identity_type == "All"
    assert all(option["disabled"] for option in identity_options)
    assert "is-disabled" in identity_class
    assert identity_value == "All"
    assert all(option["disabled"] for option in identity_value_options)

    reset_indicators = indicators("fra_survey_ii", None)
    reset_controls = controls(None, "es", None, "fra_survey_ii")
    assert reset_indicators[:3] == ([], None, True)
    assert reset_controls[3] is None
    assert reset_controls[4] == {}
    assert "is-hidden" not in reset_controls[7]
    assert "is-disabled" in reset_controls[7]
