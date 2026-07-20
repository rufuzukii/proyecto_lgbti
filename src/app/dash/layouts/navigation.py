from __future__ import annotations

from dash import html
from dash.development.base_component import Component
from flask_login import current_user

from app.dash.i18n import dash_attrs, text, text_attrs
from app.users.schemas import UserRole


def build_navbar(active: str | None = None) -> Component:
    links = [
        ("Inicio", "Home", "/", "home"),
        ("España", "Spain", "/spain", "spain"),
        ("Estadísticas", "Statistics", "/statistics", "statistics"),
        ("Informes", "Reports", "/report", "report"),
        ("Didáctica", "Didactics", "/didactics", "didactics"),
        ("Acerca de", "About", "/about", "about"),
        ("Importar datos", "Import data", "/upload", "upload"),
    ]

    return html.Nav(
        [
            html.Div(
                [
                    html.A(
                        html.Img(
                            src="/assets/img/rainbow_lens_logo.png",
                            alt="RainbowLens",
                            className="nav-brand-logo",
                        ),
                        href="/",
                        className="nav-brand",
                        title="RainbowLens",
                    ),
                    _admin_link(active),
                ],
                className="nav-left",
            ),
            html.Div(
                [
                    html.Ul(
                        [
                            html.Li(
                                html.A(
                                    text(label_es, label_en),
                                    href=href,
                                    className=_nav_link_class(key, active),
                                )
                            )
                            for label_es, label_en, href, key in links
                        ],
                        className="nav-links",
                    ),
                    html.Div(
                        [
                            _language_toggle(),
                            _theme_toggle(),
                        ],
                        className="nav-preference-actions",
                    ),
                    _account_link(),
                ],
                className="nav-actions",
            ),
        ],
        className="navbar",
    )


def _account_link() -> Component:
    if current_user.is_authenticated:
        display_name = getattr(current_user, "username", None) or getattr(current_user, "email", None)
        return html.A(
            display_name or "Cuenta",
            href="/user",
            className="nav-link nav-account",
            **text_attrs(display_name or "Cuenta", display_name or "Account"),
        )
    return html.A(
        text("Entrar", "Sign in"),
        href="/login",
        className="nav-link nav-cta nav-account",
    )


def _admin_link(active: str | None) -> Component | str:
    if not current_user.is_authenticated:
        return ""
    role = getattr(current_user, "role", None)
    role_value = role.value if isinstance(role, UserRole) else str(role)
    if role_value != UserRole.ADMIN.value:
        return ""
    class_name = "nav-link nav-admin-cta"
    if active == "admin":
        class_name += " is-active"
    return html.A(text("Administración", "Administration"), href="/admin", className=class_name)


def _language_toggle() -> Component:
    return html.Div(
        [
            html.Button(
                "ES",
                type="button",
                className="language-toggle",
                **dash_attrs({"data-language-toggle": "true"}),
            ),
            html.Span("Idioma", className="nav-control-caption", **text_attrs("Idioma", "Language")),
        ],
        className="nav-control-stack",
    )


def _theme_toggle() -> Component:
    return html.Div(
        [
            html.Button(
                html.Span(className="theme-toggle-dot"),
                type="button",
                className="theme-toggle",
                **dash_attrs({
                    "data-theme-toggle": "true",
                    "data-theme-state": "light",
                }),
            ),
            html.Span(
                "Modo claro",
                className="nav-control-caption theme-mode-caption",
                **dash_attrs({"data-theme-label": "true", **text_attrs("Modo claro", "Light mode")}),
            ),
        ],
        className="nav-control-stack",
    )


def _nav_link_class(key: str, active: str | None) -> str:
    classes = ["nav-link"]
    if key == active:
        classes.append("is-active")
    if key == "upload":
        classes.append("nav-cta")
    return " ".join(classes)
