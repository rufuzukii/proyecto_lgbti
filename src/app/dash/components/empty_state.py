from __future__ import annotations

from dash import html
from dash.development.base_component import Component


def build_empty_state(
    title: str,
    description: str | None = None,
    *,
    class_name: str = "app-empty-state",
) -> Component:
    """Build an accessible, presentation-only state for deferred or empty results."""

    children: list[Component] = [html.H2(title)]
    if description:
        children.append(html.P(description))
    return html.Div(children, className=class_name, role="status", **{"aria-live": "polite"})
