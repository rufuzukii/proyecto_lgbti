from __future__ import annotations

from dash import dcc, html
from dash.development.base_component import Component
from flask_login import current_user

from app.auth.permissions import Permission, user_has_permission
from app.dash.components.section_navigation import PRIMARY_NAVIGATION_SECTIONS
from app.dash.i18n import attribute_attrs, dash_attrs, text, text_attrs, ui_text
from app.dash.routes import route_path
from app.users.schemas import UserRole


def build_navbar(active: str | None = None) -> Component:
    links = [
        (
            ui_text(section.label_key, "es"),
            ui_text(section.label_key, "en"),
            section.key,
            section.key,
        )
        for section in PRIMARY_NAVIGATION_SECTIONS
    ]
    links.extend(
        [
            ("Importar datos", "Import data", "upload", "upload"),
        ]
    )
    if not user_has_permission(current_user, Permission.UPLOAD_DATA):
        links = [link for link in links if link[3] != "upload"]
    if not user_has_permission(current_user, Permission.GENERATE_REPORTS):
        links = [link for link in links if link[3] != "reports"]
    admin_link = _admin_link(active)
    navbar_class = "navbar navbar--admin" if admin_link is not None else "navbar"

    return html.Nav(
        [
            dcc.Link(
                [
                    html.Img(
                        src="/assets/img/rainbow_lens_logo.png?v=20260821",
                        alt="RainbowLens DataHub",
                        className="nav-brand-logo nav-brand-logo-desktop",
                    ),
                    html.Img(
                        src="/assets/img/rainbow_lens_icono.png?v=20260821",
                        alt="RainbowLens DataHub",
                        className="nav-brand-logo nav-brand-logo-mobile",
                    ),
                ],
                href=route_path("home"),
                refresh=False,
                className="nav-brand",
                title="RainbowLens DataHub · Inicio / Home",
            ),
            html.Div(
                [
                    _language_toggle(),
                    _theme_toggle(),
                    html.Div(
                        _account_link(),
                        className="nav-account-slot nav-account-slot-desktop",
                    ),
                ],
                className="nav-header-actions",
            ),
            html.Button(
                [
                    html.Span(className="nav-menu-icon", **dash_attrs({"aria-hidden": "true"})),
                    html.Span(
                        "Abrir menú",
                        className="sr-only",
                        **text_attrs("Abrir menú", "Open menu"),
                    ),
                ],
                type="button",
                className="nav-menu-toggle",
                title="Menú",
                **dash_attrs(
                    {
                        "data-nav-menu-toggle": "true",
                        "aria-controls": "primary-navigation",
                        "aria-expanded": "false",
                        "aria-label": "Abrir menú",
                        **attribute_attrs("title", "Menú", "Menu"),
                        **attribute_attrs("aria-label", "Abrir menú", "Open menu"),
                    }
                ),
            ),
            html.Div(
                [
                    html.Div(admin_link, className="nav-admin-slot"),
                    html.Ul(
                        [
                            html.Li(
                                dcc.Link(
                                    text(label_es, label_en),
                                    href=route_path(href),
                                    className=_nav_link_class(key, active),
                                )
                            )
                            for label_es, label_en, href, key in links
                        ],
                        className="nav-links",
                    ),
                    html.Div(
                        _account_link(),
                        className="nav-account-slot nav-account-slot-mobile",
                    ),
                ],
                id="primary-navigation",
                className="nav-menu",
            ),
        ],
        className=navbar_class,
        **dash_attrs(
            {
                "aria-label": "Navegación principal",
                **attribute_attrs(
                    "aria-label",
                    "Navegación principal",
                    "Primary navigation",
                ),
            }
        ),
    )


def _account_link() -> Component:
    if current_user.is_authenticated:
        display_name = getattr(current_user, "username", None) or getattr(
            current_user, "email", None
        )
        return dcc.Link(
            html.Span(
                [
                    text(
                        display_name or "Cuenta",
                        display_name or "Account",
                        class_name="nav-account-name",
                    ),
                    text(
                        "Panel personal",
                        "Personal dashboard",
                        class_name="nav-account-caption",
                    ),
                ],
                className="nav-account-copy",
            ),
            href=route_path("profile"),
            className="nav-link nav-account",
        )
    return dcc.Link(
        text("Entrar", "Sign in"),
        href=route_path("login"),
        className="nav-link nav-cta nav-account",
    )


def _admin_link(active: str | None) -> Component | None:
    if not current_user.is_authenticated:
        return None
    role = getattr(current_user, "role", None)
    role_value = role.value if isinstance(role, UserRole) else str(role)
    if role_value != UserRole.ADMIN.value:
        return None
    class_name = "nav-link nav-admin-cta"
    if active == "admin":
        class_name += " is-active"
    return dcc.Link(
        text("Administración", "Administration"),
        href=route_path("admin"),
        className=class_name,
    )


def _language_toggle() -> Component:
    return html.Div(
        [
            html.Button(
                "ES",
                type="button",
                className="language-toggle",
                **dash_attrs(
                    {
                        "data-language-toggle": "true",
                        "aria-label": "Cambiar idioma / Change language",
                    }
                ),
            ),
            html.Span(
                "Idioma", className="nav-control-caption", **text_attrs("Idioma", "Language")
            ),
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
                **dash_attrs(
                    {
                        "data-theme-toggle": "true",
                        "aria-label": "Cambiar modo de color / Change color mode",
                    }
                ),
            ),
            html.Span(
                "Modo claro",
                className="nav-control-caption theme-mode-caption",
                **dash_attrs(
                    {"data-theme-label": "true", **text_attrs("Modo claro", "Light mode")}
                ),
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
