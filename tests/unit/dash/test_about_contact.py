from __future__ import annotations

from urllib.parse import parse_qs, unquote, urlsplit

from dash.development.base_component import Component

from app.core.contact import CONTACT_EMAIL
from app.web import about
from app.web.routes import localized_route_context


def _walk(component):
    if isinstance(component, Component):
        yield component
        children = getattr(component, "children", None)
        values = children if isinstance(children, list | tuple) else [children]
        for child in values:
            yield from _walk(child)


def _contact_link(language: str):
    with localized_route_context(language):
        layout = about._contact_section()
    return next(
        component
        for component in _walk(layout)
        if getattr(component, "href", "").startswith(f"mailto:{CONTACT_EMAIL}")
    )


def test_about_uses_direct_mailto_without_form_controls() -> None:
    with localized_route_context("es"):
        layout = about._contact_section()
    components = list(_walk(layout))
    assert any(getattr(component, "id", None) == "about-contact" for component in components)
    assert not any(component.__class__.__name__ == "Form" for component in components)
    assert not any(
        str(getattr(component, "id", "") or "").startswith("about-contact-")
        for component in components
    )


def test_spanish_mailto_contains_encoded_subject_and_body() -> None:
    link = _contact_link("es")
    query = parse_qs(urlsplit(getattr(link, "href", "")).query)
    assert link.children == CONTACT_EMAIL
    assert query["subject"] == ["Consulta sobre RainbowLens DataHub"]
    body = unquote(query["body"][0])
    assert "Nombre:" in body
    assert "Motivo de contacto:" in body
    assert "Mensaje:" in body
    assert "Correo electrónico:" not in body


def test_english_mailto_contains_localized_subject_and_body() -> None:
    link = _contact_link("en")
    query = parse_qs(urlsplit(getattr(link, "href", "")).query)
    assert query["subject"] == ["RainbowLens DataHub enquiry"]
    body = unquote(query["body"][0])
    assert "Name:" in body
    assert "Reason for contacting:" in body
    assert "Message:" in body
