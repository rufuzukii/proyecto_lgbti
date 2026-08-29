from typing import Any, cast

from dash import html

from app.shared.components.loading import contextual_loading


def test_contextual_loading_delays_spinner_and_announces_specific_operation() -> None:
    # Arrange / Act
    loading = cast(
        Any,
        contextual_loading(
            html.Div("content"),
            "loading_statistics",
            element_id="statistics-loading",
        ),
    )

    # Assert
    assert loading.id == "statistics-loading"
    assert loading.delay_show == 200
    assert loading.delay_hide == 120
    assert loading.custom_spinner.role == "status"
    assert loading.custom_spinner.to_plotly_json()["props"]["aria-live"] == "polite"
    translated_text = loading.custom_spinner.children[1]
    assert translated_text.children == "Cargando estadísticas..."
    assert translated_text.to_plotly_json()["props"]["data-i18n-en"] == "Loading statistics..."


def test_contextual_loading_can_hide_stale_content_during_a_global_refresh() -> None:
    loading = cast(
        Any,
        contextual_loading(
            html.Div("old dashboard"),
            "loading_statistics",
            target_components={"stats-data-store": "data"},
            hide_content_while_loading=True,
        ),
    )

    assert loading.overlay_style == {"visibility": "hidden"}
    assert "context-loading-hide-content" in loading.parent_className
    assert loading.target_components == {"stats-data-store": "data"}


def test_contextual_loading_can_render_spinner_without_visible_copy() -> None:
    loading = cast(
        Any,
        contextual_loading(
            html.Div("content"),
            "loading_statistics",
            show_message=False,
        ),
    )

    accessible_label = loading.custom_spinner.children[1]
    assert accessible_label.className == "sr-only"
    assert accessible_label.children.children == "Cargando estadísticas..."
    assert loading.custom_spinner.children[0].className == "context-loading-spinner"
