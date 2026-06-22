from __future__ import annotations

from app.dash.compat import html


def text_attrs(es: str, en: str) -> dict[str, str]:
    return {
        "data-i18n-es": es,
        "data-i18n-en": en,
    }


def text(es: str, en: str, *, class_name: str | None = None) -> html.Span:
    props = text_attrs(es, en)
    if class_name:
        props["className"] = class_name
    return html.Span(es, **props)
