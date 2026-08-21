from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from dash import dcc

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
    document_queries = []
    monkeypatch.setattr(
        spain,
        "get_felgtbi_document_options",
        lambda **kwargs: document_queries.append(kwargs)
        or [
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
    document_label = _find(layout, "spain-document-select-label")
    indicator = _find(layout, "spain-topic-select")

    # Assert
    assert "spain-source-select" not in ids
    assert "spain-category-select" not in ids
    assert year.to_plotly_json()["props"]["value"] == 2026
    assert [option["value"] for option in year.options] == [2026, 2025]
    assert document_queries == [{"year": 2026}]
    assert isinstance(document, dcc.RadioItems)
    document_props = document.to_plotly_json()["props"]
    assert document_props["value"] is None
    assert [option["value"] for option in document_props["options"]] == [
        "doc-odio",
        "doc-voto",
    ]
    assert "spain-selection-control" in document_props["className"]
    assert document_label.to_plotly_json()["type"] == "Span"
    assert "htmlFor" not in document_label.to_plotly_json()["props"]
    document_group = next(
        item
        for item in _walk(layout)
        if item is not document_label
        and hasattr(item, "to_plotly_json")
        and item.to_plotly_json()["props"].get("role") == "group"
        and item.to_plotly_json()["props"].get("aria-labelledby")
        == "spain-document-select-label"
    )
    assert document_group.className.endswith("spain-document-field")
    assert indicator.value is None


def test_spain_layout_falls_back_to_most_recent_available_year(monkeypatch) -> None:
    monkeypatch.setattr(spain, "get_felgtbi_years", lambda: [2024, 2025, 2024])
    requested_years = []
    monkeypatch.setattr(
        spain,
        "get_felgtbi_document_options",
        lambda **kwargs: requested_years.append(kwargs["year"]) or [],
    )
    monkeypatch.setattr(spain, "build_navbar", lambda **_kwargs: None)

    layout = spain.build_spain_layout()

    year = _find(layout, "spain-year-select")
    assert year.value == 2025
    assert [option["value"] for option in year.options] == [2025, 2024]
    assert requested_years == [2025]


def test_document_selector_queries_only_the_selected_year_and_resets_selection(
    monkeypatch,
) -> None:
    documents_by_year = {
        2025: [
            {"label": "Documento A", "value": "2025-a"},
            {"label": "Documento B", "value": "2025-b"},
        ],
        2026: [
            {"label": "Documento C", "value": "2026-c"},
            {"label": "Documento D", "value": "2026-d"},
        ],
    }
    requested_years = []

    def document_options(*, year: int) -> list[dict[str, str]]:
        requested_years.append(year)
        return documents_by_year[year]

    monkeypatch.setattr(spain, "get_felgtbi_document_options", document_options)

    initial_options, initial_value = spain._document_selector_state(2026)
    changed_options, changed_value = spain._document_selector_state(2025)

    assert requested_years == [2026, 2025]
    assert [option["value"] for option in initial_options] == ["2026-c", "2026-d"]
    assert [option["value"] for option in changed_options] == ["2025-a", "2025-b"]
    assert initial_value is None
    assert changed_value is None


def test_document_selector_never_queries_all_years_without_a_valid_year(monkeypatch) -> None:
    queries = []
    monkeypatch.setattr(
        spain,
        "get_felgtbi_document_options",
        lambda **kwargs: queries.append(kwargs) or [],
    )

    assert spain._document_selector_state(None) == ([], None)
    assert spain._document_selector_state("not-a-year") == ([], None)
    assert queries == []


def test_spain_indicator_dropdown_keeps_its_natural_height() -> None:
    css = Path("src/app/dash/assets/statistics.css").read_text(encoding="utf-8")
    selector_rule = css.split(".spain-topic-selector-row {", maxsplit=1)[1].split(
        "}", maxsplit=1
    )[0]

    assert "align-items: start;" in selector_rule
    assert "align-items: stretch;" not in selector_rule
    assert "overflow: hidden;" not in selector_rule
    assert ".spain-dropdown .dash-dropdown-trigger" in css
    assert ".spain-dropdown,\n.spain-dropdown .Select-control" in css


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


def test_indicator_navigation_selects_first_option_when_document_is_chosen() -> None:
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
    assert initial == ("one", "ok")
    assert next_value == ("two", "ok")
    assert bounded == ("two", "ok")


def test_indicator_navigation_selects_first_option_when_previous_value_disappears() -> None:
    options = [
        {"label": "Uno", "value": "one"},
        {"label": "Dos", "value": "two"},
    ]

    selected = spain._resolve_topic_selection(
        options,
        "old-indicator",
        trigger_id="spain-document-select",
    )

    assert selected == ("one", "removed")
