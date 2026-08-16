from __future__ import annotations

import logging

from app.taxonomy import (
    canonical_taxonomy_value,
    taxonomy_label,
    taxonomy_labels,
    taxonomy_pair,
)


def test_taxonomy_returns_spanish_and_english_without_changing_canonical_value() -> None:
    # Arrange
    canonical = "Sexual Orientation"

    # Act
    labels = taxonomy_pair("fra_filter", canonical)

    # Assert
    assert labels == ("Orientaci\u00f3n sexual", "Sexual orientation")
    assert canonical_taxonomy_value("fra_filter", canonical) == canonical


def test_language_change_only_changes_visible_label() -> None:
    # Arrange
    canonical = "Equality & non-discrimination"

    # Act
    spanish = taxonomy_label("ilga_category", canonical, "es")
    english = taxonomy_label("ilga_category", canonical, "en")

    # Assert
    assert spanish == "Igualdad y no discriminaci\u00f3n"
    assert english == "Equality and non-discrimination"
    assert canonical_taxonomy_value("ilga_category", canonical) == canonical


def test_old_role_aliases_are_normalized_to_stable_internal_values() -> None:
    assert canonical_taxonomy_value("role", "profesor") == "docente"
    assert canonical_taxonomy_value("role", "teacher") == "docente"
    assert canonical_taxonomy_value("role", "common") == "comun"
    assert taxonomy_label("role", "politician", "es") == "Pol\u00edtico"


def test_multiple_responses_keep_order_and_translate_independently() -> None:
    # Arrange
    responses = ["Yes", "No", "Don't know", "Prefer not to say"]

    # Act
    translated = taxonomy_labels("fra_response", responses, "es")

    # Assert
    assert translated == ["S\u00ed", "No", "No lo sabe", "Prefiere no responder"]


def test_categories_with_symbols_and_accents_match_aliases() -> None:
    assert (
        canonical_taxonomy_value("ilga_category", "Equality and non-discrimination")
        == "Equality & non-discrimination"
    )
    assert taxonomy_label("felgtbi_topic", "LGBTIQ+ youth", "es") == "Juventud LGBTIQ+"
    assert (
        taxonomy_label("fra_category", "Living openly and daily life", "es")
        == "Vida abierta y vida cotidiana"
    )


def test_unknown_value_uses_controlled_fallback_and_is_logged_once(caplog) -> None:
    # Arrange
    unknown = "A new canonical value"

    # Act
    with caplog.at_level(logging.WARNING, logger="app.taxonomy"):
        first = taxonomy_label("fra_category", unknown, "es")
        second = taxonomy_label("fra_category", unknown, "en")

    # Assert
    assert first == second == unknown
    messages = [record.message for record in caplog.records if record.message == "taxonomy_label_missing"]
    assert len(messages) == 1
