from __future__ import annotations

from dash import html
from dash.development.base_component import Component

from app.web.i18n import dash_attrs


def build_empty_state(
    title: str | Component,
    description: str | Component | None = None,
    *,
    class_name: str = "app-empty-state",
) -> Component:
    """Construye un estado accesible de presentación para resultados pendientes o vacíos."""

    children: list[Component] = [html.H2(title)]
    if description:
        children.append(html.P(description))
    return html.Div(
        children,
        className=class_name,
        role="status",
        **dash_attrs({"aria-live": "polite"}),
    )
