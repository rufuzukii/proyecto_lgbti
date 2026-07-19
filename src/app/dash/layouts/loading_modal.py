from __future__ import annotations

from app.dash.compat import html
from app.dash.i18n import text_attrs


def build_loading_modal(
    *,
    element_id: str,
    title: tuple[str, str],
    description: tuple[str, str],
    hidden: bool = True,
) -> html.Div:
    title_es, title_en = title
    description_es, description_en = description
    class_name = "upload-loading-overlay"
    if hidden:
        class_name += " is-hidden"
    return html.Div(
        html.Div(
            [
                html.Div(className="upload-loading-spinner", **{"aria-hidden": "true"}),
                html.H2(title_es, **text_attrs(title_es, title_en)),
                html.P(description_es, **text_attrs(description_es, description_en)),
            ],
            className="upload-loading-dialog",
            role="dialog",
            **{"aria-modal": "true", "aria-live": "assertive"},
        ),
        id=element_id,
        className=class_name,
    )
