from __future__ import annotations

from flask_login import current_user

from app.dash.compat import html
from app.users.schemas import UserRole


def build_navbar(active: str | None = None) -> html.Nav:
    links = [
        ("Home", "/", "home"),
        ("Stadistics", "/stadistics", "stadistics"),
        ("Report", "/report", "report"),
        ("Didactics", "/didactics", "didactics"),
        ("About", "/about", "about"),
        ("Import CSV", "/upload", "upload"),
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
                                    label,
                                    href=href,
                                    className=_nav_link_class(key, active),
                                )
                            )
                            for label, href, key in links
                        ],
                        className="nav-links",
                    ),
                    _account_link(),
                ],
                className="nav-actions",
            ),
        ],
        className="navbar",
    )


def _account_link() -> html.A:
    if current_user.is_authenticated:
        display_name = getattr(current_user, "username", None) or getattr(current_user, "email", None)
        return html.A(display_name or "Account", href="/user", className="nav-link nav-account")
    return html.A("Sign in", href="/login", className="nav-link nav-cta nav-account")


def _admin_link(active: str | None) -> html.A | str:
    if not current_user.is_authenticated:
        return ""
    role = getattr(current_user, "role", None)
    role_value = role.value if isinstance(role, UserRole) else str(role)
    if role_value != UserRole.ADMIN.value:
        return ""
    class_name = "nav-link nav-admin-cta"
    if active == "admin":
        class_name += " is-active"
    return html.A("Admin", href="/admin", className=class_name)


def _nav_link_class(key: str, active: str | None) -> str:
    classes = ["nav-link"]
    if key == active:
        classes.append("is-active")
    if key == "upload":
        classes.append("nav-cta")
    return " ".join(classes)
