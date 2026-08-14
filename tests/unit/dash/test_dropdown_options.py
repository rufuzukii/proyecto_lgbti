from __future__ import annotations

import logging

from app.dash.components.dropdown_options import (
    build_dropdown_options,
    option_value_or_none,
)


def test_dropdown_options_discard_invalid_and_duplicate_values(caplog) -> None:
    caplog.set_level(logging.WARNING)

    options = build_dropdown_options(
        [
            {"label": " First ", "value": " first "},
            {"label": None, "value": "missing-label"},
            {"label": "Missing value", "value": None},
            {"label": "Nested", "value": {"id": 1}},
            {"label": "Duplicate", "value": "first"},
            {"label": "Second", "value": 2, "disabled": True},
        ],
        context="test-options",
    )

    assert options == [
        {"label": "First", "value": "first"},
        {"label": "Second", "value": 2, "disabled": True},
    ]
    assert "dropdown_options_discarded context=test-options" in caplog.text


def test_dropdown_options_preserve_stable_input_order() -> None:
    items = [
        {"label": "Zulu", "value": "z"},
        {"label": "Alpha", "value": "a"},
    ]

    assert [option["value"] for option in build_dropdown_options(items)] == ["z", "a"]


def test_option_value_is_cleared_when_new_options_do_not_contain_it() -> None:
    options = build_dropdown_options(
        [{"label": "Social attitudes", "value": "social-attitudes"}]
    )

    assert option_value_or_none(options, "old-category-indicator") is None
    assert option_value_or_none(options, "social-attitudes") == "social-attitudes"
