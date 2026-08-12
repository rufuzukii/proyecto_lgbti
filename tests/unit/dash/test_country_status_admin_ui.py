from typing import Any

from dash import Dash

from app.dash.layouts.home import (
    _any_clicks,
    _country_status_card,
    _country_status_editor,
    _empty_country_status_editor_record,
    build_home_layout,
    register_home_callbacks,
)

STATUS = {
    "available": True,
    "country_code": "ES",
    "country": "Spain",
    "year": 2026,
    "title": "Situacion general",
    "summary": "Resumen cualitativo suficientemente largo.",
    "legal_context": "",
    "social_context": "",
    "positive_developments": [],
    "main_challenges": [],
    "source_name": "ILGA-Europe Annual Review 2026",
    "source_url": "https://example.test/report.pdf",
    "reviewed_at": "2026-03-15",
    "active": True,
}


def test_admin_country_status_card_renders_edit_button() -> None:
    card = _country_status_card(STATUS, {"ES": "Spain"}, 2026, can_manage=True)

    assert _contains_text(card, "Editar")


def test_non_admin_country_status_card_omits_edit_button() -> None:
    card = _country_status_card(STATUS, {"ES": "Spain"}, 2026, can_manage=False)

    assert not _contains_text(card, "Editar")


def test_admin_missing_country_status_card_renders_add_button() -> None:
    missing = {
        **STATUS,
        "available": False,
        "summary": "Todavía no hay información disponible para este país.",
        "summary_i18n": {
            "es": "Todavía no hay información disponible para este país.",
            "en": "No information is available for this country yet.",
        },
    }
    card = _country_status_card(missing, {"ES": "Spain"}, 2026, can_manage=True)
    empty_summary = _find_component_by_class(card, "country-status-card__empty")
    empty_summary_props = empty_summary.to_plotly_json()["props"]

    assert _contains_text(card, "Añadir información")
    assert (
        empty_summary_props["data-i18n-es"]
        == "Todavía no hay información disponible para este país."
    )
    assert (
        empty_summary_props["data-i18n-en"] == "No information is available for this country yet."
    )


def test_home_country_status_editor_callbacks_use_existing_store_ids(monkeypatch) -> None:
    monkeypatch.setattr("app.dash.layouts.home.build_navbar", lambda active=None: "")
    monkeypatch.setattr("app.dash.layouts.home.get_latest_ilga_document", lambda: None)
    monkeypatch.setattr("app.dash.layouts.home.get_ilga_years", list)

    app = Dash(__name__, suppress_callback_exceptions=True)
    app.layout = build_home_layout()
    register_home_callbacks(app)

    layout_ids = _component_ids(app.layout)
    callback_outputs = {
        output.component_id
        for callback in app.callback_map.values()
        for output in _callback_outputs(callback["output"])
        if isinstance(output.component_id, str)
    }

    assert "home-country-status-editor-state" in layout_ids
    assert "country-status-editor-state" not in callback_outputs
    assert callback_outputs.issubset(layout_ids)
    callback_inputs = {
        item["id"] for callback in app.callback_map.values() for item in callback["inputs"]
    }
    joined_inputs = " ".join(callback_inputs)
    assert "country-status-open-editor" in joined_inputs
    assert '"type":"country-status-edit"' not in joined_inputs
    assert '"type":"country-status-add"' not in joined_inputs


def test_home_legal_map_helper_text_is_registered(monkeypatch) -> None:
    monkeypatch.setattr("app.dash.layouts.home.build_navbar", lambda active=None: "")
    monkeypatch.setattr(
        "app.dash.layouts.home.get_latest_ilga_document",
        lambda: {"year": 2026, "countries": []},
    )
    monkeypatch.setattr("app.dash.layouts.home.get_ilga_years", lambda: [2026])

    app = Dash(__name__, suppress_callback_exceptions=True)
    app.layout = build_home_layout()
    register_home_callbacks(app)

    helper = _find_component_by_id(app.layout, "home-map-helper-text")
    footer_meta = _find_component_by_class(app.layout, "home-map-footer-meta")
    summary = _find_component_by_class(app.layout, "home-map-summary")
    helper_props = helper.to_plotly_json()["props"]
    callback_outputs = {
        output.component_id
        for callback in app.callback_map.values()
        for output in _callback_outputs(callback["output"])
        if isinstance(output.component_id, str)
    }

    assert "Selecciona un país para consultar la situación legal actual" in _text_content(helper)
    assert (
        helper_props["data-i18n-en"]
        == "Select a country to view the current legal situation of LGBTIQ+ people."
    )
    assert helper_props["className"] == "home-map-helper-text"
    assert type(helper).__name__ == "H2"
    footer_children = footer_meta.to_plotly_json()["props"]["children"]
    assert [child.id for child in footer_children] == ["home-map-source"]
    summary_children = summary.to_plotly_json()["props"]["children"]
    summary_header = summary_children[0]
    summary_metrics = summary_children[1]
    assert summary_header.className == "home-map-summary-header"
    assert [getattr(child, "id", None) for child in summary_header.children] == [
        "home-map-copy",
        None,
    ]
    assert summary_header.children[1].href == "/es/estadisticas"
    assert summary_metrics.id == "home-map-metrics"
    assert "home-map-helper-text" in callback_outputs


def test_home_map_contains_only_legal_controls(monkeypatch) -> None:
    monkeypatch.setattr("app.dash.layouts.home.build_navbar", lambda active=None: "")
    monkeypatch.setattr(
        "app.dash.layouts.home.get_latest_ilga_document",
        lambda: {"year": 2026, "countries": []},
    )
    monkeypatch.setattr("app.dash.layouts.home.get_ilga_years", lambda: [2026])

    layout = build_home_layout()
    layout_ids = _component_ids(layout)
    map_graph = _find_component_by_id(layout, "home-main-map")
    map_props = map_graph.to_plotly_json()["props"]

    assert "home-ilga-year" in layout_ids
    assert "home-country-select" in layout_ids
    assert "home-map-mode" not in layout_ids
    assert "home-fra-category" not in layout_ids
    assert "home-fra-indicator" not in layout_ids
    assert map_props["config"]["scrollZoom"] is False
    assert map_props["config"]["doubleClick"] is False
    assert {"zoomInGeo", "zoomOutGeo", "resetGeo"}.issubset(
        map_props["config"]["modeBarButtonsToRemove"]
    )
    assert map_props["figure"].layout.dragmode is False
    assert not _contains_text(layout, "Discriminación y datos sociales")


def test_country_status_editor_ignores_dynamic_components_without_clicks() -> None:
    assert not _any_clicks([], None)
    assert not _any_clicks([None], [0])
    assert _any_clicks([None], [1])


def test_existing_country_status_requires_explicit_delete_confirmation() -> None:
    editor = _country_status_editor(
        {
            "country": "España",
            "country_code": "ES",
            "year": 2026,
            "summary": "Descripción suficientemente larga para editar el registro.",
            "source_name": "ILGA-Europe",
            "source_url": "https://www.ilga-europe.org/",
            "reviewed_at": "2026-07-29",
            "active": True,
        },
        {"mode": "edit", "country_code": "ES", "year": 2026, "exists": True},
        [{"label": "España (ES)", "value": "ES"}],
        {},
    )

    confirmation = _find_component_by_id(
        editor,
        {"type": "country-status-delete-confirm", "slot": "main"},
    )
    props = confirmation.to_plotly_json()["props"]

    assert props["options"][0]["value"] == "confirm"
    assert props["value"] == []


def test_country_status_editor_empty_record_keeps_form_blank() -> None:
    editor = _country_status_editor(
        _empty_country_status_editor_record(),
        {"mode": "create", "exists": False},
        [{"label": "Spain (ES)", "value": "ES"}],
        {},
    )

    assert (
        _find_component_by_dict_id(
            editor, {"type": "country-status-form-country", "slot": "main"}
        ).value
        == ""
    )
    assert (
        _find_component_by_dict_id(
            editor, {"type": "country-status-form-country-code", "slot": "main"}
        ).value
        == ""
    )
    assert (
        _find_component_by_dict_id(
            editor, {"type": "country-status-form-year", "slot": "main"}
        ).value
        == ""
    )
    assert (
        _find_component_by_dict_id(
            editor, {"type": "country-status-form-source-name", "slot": "main"}
        ).value
        == ""
    )
    assert (
        _find_component_by_dict_id(
            editor, {"type": "country-status-form-source-url", "slot": "main"}
        ).value
        == ""
    )
    assert (
        _find_component_by_dict_id(
            editor, {"type": "country-status-form-reviewed-at", "slot": "main"}
        ).value
        == ""
    )
    assert (
        _find_component_by_dict_id(
            editor, {"type": "country-status-form-active", "slot": "main"}
        ).value
        == []
    )


def _contains_text(component: Any, expected: str) -> bool:
    children = getattr(component, "children", None)
    if children == expected:
        return True
    if isinstance(children, str):
        return expected in children
    if isinstance(children, (list, tuple)):
        return any(_contains_text(child, expected) for child in children)
    if hasattr(children, "children"):
        return _contains_text(children, expected)
    return False


def _component_ids(component: Any) -> set[str]:
    output = set()
    component_id = getattr(component, "id", None)
    if isinstance(component_id, str):
        output.add(component_id)
    children = getattr(component, "children", None)
    if isinstance(children, (list, tuple)):
        for child in children:
            if hasattr(child, "id") or hasattr(child, "children"):
                output.update(_component_ids(child))
    elif hasattr(children, "children"):
        output.update(_component_ids(children))
    return output


def _find_component_by_id(component: Any, expected_id: Any) -> Any:
    if getattr(component, "id", None) == expected_id:
        return component
    children = getattr(component, "children", None)
    if isinstance(children, (list, tuple)):
        for child in children:
            if hasattr(child, "id") or hasattr(child, "children"):
                try:
                    return _find_component_by_id(child, expected_id)
                except AssertionError:
                    pass
    elif hasattr(children, "children"):
        return _find_component_by_id(children, expected_id)
    raise AssertionError(f"component not found: {expected_id}")


def _find_component_by_class(component: Any, expected_class: str) -> Any:
    classes = str(getattr(component, "className", "") or "").split()
    if expected_class in classes:
        return component
    children = getattr(component, "children", None)
    if isinstance(children, (list, tuple)):
        for child in children:
            if hasattr(child, "id") or hasattr(child, "children"):
                try:
                    return _find_component_by_class(child, expected_class)
                except AssertionError:
                    pass
    elif hasattr(children, "children"):
        return _find_component_by_class(children, expected_class)
    raise AssertionError(f"component with class not found: {expected_class}")


def _find_component_by_dict_id(component: Any, expected_id: dict[str, str]) -> Any:
    if getattr(component, "id", None) == expected_id:
        return component
    children = getattr(component, "children", None)
    if isinstance(children, (list, tuple)):
        for child in children:
            if hasattr(child, "id") or hasattr(child, "children"):
                try:
                    return _find_component_by_dict_id(child, expected_id)
                except AssertionError:
                    pass
    elif hasattr(children, "children"):
        return _find_component_by_dict_id(children, expected_id)
    raise AssertionError(f"component not found: {expected_id}")


def _text_content(component: Any) -> str:
    children = getattr(component, "children", None)
    if isinstance(children, str):
        return children
    if isinstance(children, (list, tuple)):
        return " ".join(_text_content(child) for child in children)
    if hasattr(children, "children"):
        return _text_content(children)
    return ""


def _callback_outputs(output: Any) -> list[Any]:
    if isinstance(output, (list, tuple)):
        return list(output)
    return [output]
