from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

from dash import html
from dash.development.base_component import Component


def _class_names(base: str, extra: str | None) -> str:
    return " ".join(part for part in (base, (extra or "").strip()) if part)


def _children(value: Component | Sequence[Component] | None) -> list[Component]:
    if value is None:
        return []
    if isinstance(value, Component):
        return [value]
    return cast(list[Component], list(value))


def build_page_header(
    *,
    title: Any,
    description: Any | None = None,
    eyebrow: Any | None = None,
    meta: Component | Sequence[Component] | None = None,
    actions: Component | Sequence[Component] | None = None,
    class_name: str | None = None,
    title_id: str | None = None,
) -> Component:
    """Construye la cabecera visual compartida de las páginas."""

    children: list[Component] = []
    if eyebrow is not None:
        children.append(html.P(eyebrow, className="app-page-eyebrow"))
    title_props: dict[str, Any] = {"className": "app-page-title"}
    if title_id is not None:
        title_props["id"] = title_id
    children.append(html.H1(title, **title_props))
    if description is not None:
        children.append(html.P(description, className="app-page-lead"))
    if meta_children := _children(meta):
        children.append(html.Div(meta_children, className="app-page-header-meta"))
    if action_children := _children(actions):
        children.append(html.Div(action_children, className="app-page-header-actions"))
    return html.Header(children, className=_class_names("app-page-header", class_name))


def surface(
    children: Any,
    *,
    class_name: str | None = None,
    element_id: str | None = None,
) -> Component:
    """Agrupa contenido relacionado en la superficie visual compartida."""

    props: dict[str, Any] = {"className": _class_names("app-surface", class_name)}
    if element_id is not None:
        props["id"] = element_id
    return html.Section(children, **props)


def page_section(
    children: Any,
    *,
    class_name: str | None = None,
    element_id: str | None = None,
) -> Component:
    """Mantiene un espaciado coherente entre secciones sin imponer una tarjeta."""

    props: dict[str, Any] = {"className": _class_names("app-page-section", class_name)}
    if element_id is not None:
        props["id"] = element_id
    return html.Section(children, **props)
