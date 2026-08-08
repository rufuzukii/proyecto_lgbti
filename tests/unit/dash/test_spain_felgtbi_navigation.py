from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from dash import dcc

from app.dash.i18n import ui_text
from app.dash.pages import spain


def _walk(component: Any):
    if component is None:
        return
    if isinstance(component, (list, tuple)):
        for child in component:
            yield from _walk(child)
        return
    yield component
    yield from _walk(getattr(component, "children", None))


def _find(component: Any, component_id: str) -> Any:
    return next(item for item in _walk(component) if getattr(item, "id", None) == component_id)


def test_spain_layout_uses_year_document_radio_indicator_hierarchy(monkeypatch) -> None:
    # Arrange
    monkeypatch.setattr(spain, "get_felgtbi_years", lambda: [2026, 2025])
    monkeypatch.setattr(
        spain,
        "get_felgtbi_document_options",
        lambda **_kwargs: [
            {"label": "Estado del odio", "value": "doc-odio"},
            {"label": "El voto en la comunidad LGTBI+", "value": "doc-voto"},
        ],
    )
    monkeypatch.setattr(spain, "build_navbar", lambda **_kwargs: None)

    # Act
    layout = spain.build_spain_layout()
    ids = {getattr(item, "id", None) for item in _walk(layout)}
    year = _find(layout, "spain-year-select")
    document = _find(layout, "spain-document-select")
    indicator = _find(layout, "spain-topic-select")

    # Assert
    assert "spain-source-select" not in ids
    assert "spain-category-select" not in ids
    assert year.value == 2026
    assert isinstance(document, dcc.RadioItems)
    assert document.value is None
    assert indicator.value is None


def test_indicator_options_keep_canonical_value_and_clean_only_label() -> None:
    # Arrange
    indicator = SimpleNamespace(
        question="Estado del odio - ¿Podría decirme cuál es su orientación sexual? - 9,60",
        specific_category="Identidad",
        value=9.6,
        report_title="Estado del odio",
        code="canonical-indicator-42",
    )

    # Act
    option = spain._indicator_options([indicator])[0]

    # Assert
    assert option == {
        "label": "¿Podría decirme cuál es su orientación sexual?",
        "value": "canonical-indicator-42",
        "title": "¿Podría decirme cuál es su orientación sexual?",
    }


def test_indicator_navigation_stays_unselected_until_user_chooses_one() -> None:
    # Arrange
    options = [
        {"label": "Uno", "value": "one"},
        {"label": "Dos", "value": "two"},
    ]

    # Act
    initial = spain._resolve_topic_selection(options, None, trigger_id="spain-document-select")
    next_value = spain._resolve_topic_selection(
        options,
        "one",
        trigger_id="spain-topic-next",
    )
    bounded = spain._resolve_topic_selection(
        options,
        "two",
        trigger_id="spain-topic-next",
    )

    # Assert
    assert initial == (None, "unselected")
    assert next_value == ("two", "ok")
    assert bounded == ("two", "ok")


def test_new_spain_control_translations_exist_in_both_languages() -> None:
    # Arrange
    keys = (
        "spain_year",
        "spain_document",
        "spain_indicator",
        "spain_select_year",
        "spain_select_document",
        "spain_select_indicator",
        "spain_previous",
        "spain_next",
        "spain_no_documents",
        "spain_no_content",
        "spain_figure",
        "spain_source",
    )

    # Act / Assert
    assert all(ui_text(key, "es") != key for key in keys)
    assert all(ui_text(key, "en") != key for key in keys)
