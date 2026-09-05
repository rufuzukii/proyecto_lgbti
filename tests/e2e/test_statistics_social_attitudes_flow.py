from __future__ import annotations

from types import SimpleNamespace

from dash import Dash

import app.modules.statistics.page as statistics_page
from app.modules.statistics.service import build_fra_control_payload


def _callback(app: Dash, name: str):
    return next(
        value["callback"].__wrapped__
        for value in app.callback_map.values()
        if getattr(value.get("callback"), "__wrapped__", None)
        and value["callback"].__wrapped__.__name__ == name
    )


def test_social_attitudes_category_round_trip_keeps_stable_dropdown_state(monkeypatch) -> None:
    social = "Social attitudes and government response"
    app = Dash("social-attitudes-state-e2e", suppress_callback_exceptions=True)
    statistics_page.register_statistics_callbacks(app)
    categories_callback = _callback(app, "update_categories_for_survey")
    indicators_callback = _callback(app, "update_fra_indicators")
    controls_callback = _callback(app, "update_fra_controls")
    demographic_values_callback = _callback(app, "update_demographic_values")
    identity_state_callback = _callback(app, "update_identity_filter_state")
    identity_values_callback = _callback(app, "update_identity_values")
    load_callback = _callback(app, "load_statistics_data")

    monkeypatch.setattr(
        statistics_page,
        "get_fra_categories",
        lambda _year=None: ["Discrimination", social, "Education"],
    )
    monkeypatch.setattr(
        statistics_page,
        "get_fra_mongo_indicators_by_category",
        lambda category, _year: [
            SimpleNamespace(
                code="D5" if category == social else "D1",
                question="Effectiveness of government" if category == social else "Discrimination",
                label=category,
            )
        ],
    )
    monkeypatch.setattr(
        statistics_page,
        "get_fra_control_payload",
        lambda code, *_args: {
            "code": code,
            "category": social if code == "D5" else "Discrimination",
            "answers": [{"label": "Yes", "value": "Yes"}],
            "segmentations": [
                {"label": "All", "value": "All"},
                {"label": "Age", "value": "Age"},
                {"label": "Sexual Orientation", "value": "Sexual Orientation"},
            ],
            "values": {
                "All": [{"label": "All", "value": "All"}],
                "Age": [{"label": "25-39", "value": "25-39"}],
                "Sexual Orientation": [{"label": "Asexual", "value": "Asexual"}],
            },
        },
    )
    monkeypatch.setattr(
        statistics_page,
        "ctx",
        type("Context", (), {"triggered_id": "app-language-store"})(),
    )

    category_options, category_value, catalog = categories_callback("fra_survey_iii", "en", social)
    assert category_value == social
    assert catalog["year"] == 2023
    assert all(isinstance(option["label"], str) for option in category_options)
    assert all(isinstance(option["value"], str) for option in category_options)

    social_options, social_value, social_disabled, cleared_result, indicator_catalog = (
        indicators_callback("fra_survey_iii", social)
    )
    assert social_options == [{"label": "Effectiveness of government", "value": "D5"}]
    assert social_value is None
    assert social_disabled is False
    assert cleared_result is None
    assert indicator_catalog == {
        "survey_id": "fra_survey_iii",
        "category": social,
        "loaded": True,
        "has_data": True,
    }

    controls_result = controls_callback("D5", "en", social, "fra_survey_iii")
    answer_options, answer_value = controls_result[:2]
    assert answer_options == [{"label": "Yes", "value": "Yes"}]
    assert answer_value == "Yes"
    assert controls_result[8] is False
    assert "is-hidden" not in controls_result[7]
    assert "is-disabled" not in controls_result[7]
    assert "is-disabled" not in controls_result[9]
    demographic_by_value = {option["value"]: option for option in controls_result[2]}
    assert demographic_by_value["Age"]["disabled"] is False

    payload = statistics_page.get_fra_control_payload("D5")
    age_options, age_value = demographic_values_callback("Age", payload, None)
    assert age_options == [{"label": "25-39", "value": "25-39"}]
    assert age_value is None

    identity_options, identity_type, identity_class = identity_state_callback(
        "Age", payload, "en", "Sexual Orientation"
    )
    assert identity_type == "All"
    assert all(option["disabled"] for option in identity_options)
    assert "is-disabled" in identity_class
    identity_value_options, identity_value = identity_values_callback(
        "Sexual Orientation", payload, "Age", "Asexual"
    )
    assert identity_value == "All"
    assert identity_value_options[0]["disabled"] is True

    enabled_options, enabled_type, enabled_class = identity_state_callback(
        "All", payload, "en", "All"
    )
    assert enabled_type == "All"
    assert any(not option.get("disabled", False) for option in enabled_options)
    assert "is-disabled" not in enabled_class

    queries = []
    monkeypatch.setattr(
        statistics_page,
        "get_fra_statistics",
        lambda query: queries.append(query) or {"status": "empty", "data": [], "ranking": []},
    )
    monkeypatch.setattr(
        statistics_page,
        "ctx",
        type("Context", (), {"triggered_id": "fra-demographic-type"})(),
    )
    base_arguments = (
        "fra_survey_iii",
        social,
        "D5",
        "Yes",
    )
    load_callback(*base_arguments, "All", "All", "All", "All", payload)
    load_callback(
        *base_arguments,
        "All",
        "All",
        "Sexual Orientation",
        "Asexual",
        payload,
    )
    load_callback(
        *base_arguments,
        "Age",
        "25-39",
        "Sexual Orientation",
        "Asexual",
        payload,
    )
    assert [
        (
            query.filter_a_name,
            query.filter_a_value,
            query.filter_b_name,
            query.filter_b_value,
        )
        for query in queries
    ] == [
        ("All", "All", "All", "All"),
        ("All", "All", "Sexual Orientation", "Asexual"),
        ("Age", "25-39", "All", "All"),
    ]

    other_options, other_value, _, _, _ = indicators_callback("fra_survey_iii", "Discrimination")
    assert other_options == [{"label": "Discrimination", "value": "D1"}]
    assert other_value is None

    returned_options, returned_value, returned_disabled, _, _ = indicators_callback(
        "fra_survey_iii", social
    )
    assert returned_options == social_options
    assert returned_value is None
    assert returned_disabled is False


def test_ranked_reason_indicator_shows_ordered_answers_and_methodology(monkeypatch) -> None:
    app = Dash("ranked-reason-state-e2e", suppress_callback_exceptions=True)
    statistics_page.register_statistics_callbacks(app)
    controls_callback = _callback(app, "update_fra_controls")
    payload = build_fra_control_payload(
        {
            "question": "insufficient income",
            "specific_category": "Reason for housing difficulties - financial problems",
            "answers": [
                {"answer": answer, "country": "Spain", "filters": []}
                for answer in ("Not Selected", "3rd", "1st", "2nd")
            ],
        }
    )
    monkeypatch.setattr(statistics_page, "get_fra_control_payload", lambda *_args: payload)

    spanish = controls_callback("G22_I", "es", "Living openly as LGBTIQ", "fra_survey_iii")
    english = controls_callback("G22_I", "en", "Living openly as LGBTIQ", "fra_survey_iii")

    assert [option["value"] for option in spanish[0]] == [
        "1st",
        "2nd",
        "3rd",
        "Not Selected",
    ]
    assert [option["label"] for option in spanish[0]] == [
        "1st",
        "2nd",
        "3rd",
        "Not Selected",
    ]
    assert "¿Cómo interpretar estas respuestas?" in str(spanish[5])
    assert spanish[6] == "stats-response-help"
    assert "How should these responses be interpreted?" in str(english[5])
