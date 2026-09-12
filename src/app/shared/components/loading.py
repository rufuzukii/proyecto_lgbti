from __future__ import annotations

from typing import Any, cast

from dash import dcc, html
from dash.development.base_component import Component

from app.web.i18n import dash_attrs, text, ui_text


def contextual_loading(
    children: Component | list[Component],
    message_key: str,
    *,
    element_id: str | None = None,
    target_components: dict[str, str | list[str]] | None = None,
    hide_content_while_loading: bool = False,
    message_id: str | None = None,
    show_message: bool = True,
) -> Component:
    """Superposición de carga accesible y diferida, con contexto visible opcional."""
    id_props: Any = {"id": element_id} if element_id else {}
    loading_label = text(ui_text(message_key, "es"), ui_text(message_key, "en"))
    label_props: dict[str, Any] = {"id": message_id} if message_id else {}
    if not show_message:
        label_props["className"] = "sr-only"
    return dcc.Loading(
        children,
        **id_props,
        delay_show=200,
        delay_hide=120,
        target_components=cast(Any, target_components),
        custom_spinner=html.Div(
            [
                html.Span(
                    className="context-loading-spinner", **dash_attrs({"aria-hidden": "true"})
                ),
                (
                    html.Span(
                        loading_label,
                        **label_props,
                    )
                    if message_id or not show_message
                    else loading_label
                ),
            ],
            className="context-loading-message",
            role="status",
            **dash_attrs({"aria-live": "polite"}),
        ),
        overlay_style=(
            {"visibility": "hidden"}
            if hide_content_while_loading
            else {
                "visibility": "visible",
                "backgroundColor": "color-mix(in srgb, var(--color-bg) 76%, transparent)",
            }
        ),
        parent_className=(
            "context-loading-wrapper context-loading-hide-content"
            if hide_content_while_loading
            else "context-loading-wrapper"
        ),
    )
