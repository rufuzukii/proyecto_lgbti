from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Literal
from urllib.parse import unquote, urlsplit

Language = Literal["es", "en"]
SUPPORTED_LANGUAGES: tuple[Language, ...] = ("es", "en")
DEFAULT_LANGUAGE: Language = "es"


@dataclass(frozen=True, slots=True)
class AppRoute:
    route_id: str
    es: str
    en: str

    def path(self, language: Language) -> str:
        return self.en if language == "en" else self.es


@dataclass(frozen=True, slots=True)
class RouteMatch:
    route_id: str
    language: Language
    path: str
    public_id: str = ""


_ROUTE_DEFINITIONS = (
    AppRoute("home", "/es", "/en"),
    AppRoute("statistics", "/es/estadisticas", "/en/statistics"),
    AppRoute("trends", "/es/tendencias", "/en/trends"),
    AppRoute("spain", "/es/espana", "/en/spain"),
    AppRoute("didactica", "/es/didactica", "/en/learning"),
    AppRoute("dictionary", "/es/didactica/diccionario", "/en/learning/dictionary"),
    AppRoute(
        "presentations",
        "/es/didactica/presentaciones",
        "/en/learning/presentations",
    ),
    AppRoute("games", "/es/didactica/juegos", "/en/learning/games"),
    AppRoute(
        "word_search",
        "/es/didactica/juegos/sopa-de-letras",
        "/en/learning/games/word-search",
    ),
    AppRoute("educators", "/es/didactica/docentes", "/en/learning/educators"),
    AppRoute(
        "educator_create",
        "/es/didactica/docentes/crear",
        "/en/learning/educators/create",
    ),
    AppRoute(
        "educator_activity",
        "/es/didactica/docentes/actividad",
        "/en/learning/educators/activity",
    ),
    AppRoute(
        "educator_public_activity",
        "/es/didactica/juegos/actividad",
        "/en/learning/games/activity",
    ),
    AppRoute("about", "/es/acerca-de", "/en/about"),
    AppRoute("reports", "/es/informe", "/en/report"),
    AppRoute("privacy", "/es/privacidad", "/en/privacy"),
    AppRoute(
        "privacy_deleted",
        "/es/privacidad/cuenta-eliminada",
        "/en/privacy/account-deleted",
    ),
    AppRoute("profile", "/es/perfil", "/en/profile"),
    AppRoute("login", "/es/iniciar-sesion", "/en/sign-in"),
    AppRoute("register", "/es/registro", "/en/register"),
    AppRoute("admin", "/es/administracion", "/en/admin"),
    AppRoute(
        "admin_imports",
        "/es/administracion/importaciones",
        "/en/admin/imports",
    ),
    AppRoute("upload", "/es/importar", "/en/upload"),
)

ROUTES: dict[str, AppRoute] = {route.route_id: route for route in _ROUTE_DEFINITIONS}
ROUTE_TITLES: dict[str, dict[Language, str]] = {
    "home": {"es": "Inicio", "en": "Home"},
    "statistics": {"es": "Estadísticas", "en": "Statistics"},
    "trends": {"es": "Tendencias", "en": "Trends"},
    "spain": {"es": "España", "en": "Spain"},
    "didactica": {"es": "Didáctica", "en": "Learning"},
    "dictionary": {"es": "Diccionario LGBTIQ+", "en": "LGBTIQ+ Dictionary"},
    "presentations": {"es": "Presentaciones", "en": "Presentations"},
    "games": {"es": "Juegos", "en": "Games"},
    "word_search": {"es": "Sopa de letras", "en": "Word search"},
    "educators": {"es": "Docentes", "en": "Educators"},
    "educator_create": {"es": "Crear actividad", "en": "Create activity"},
    "educator_activity": {"es": "Actividad docente", "en": "Educator activity"},
    "educator_public_activity": {"es": "Actividad", "en": "Activity"},
    "about": {"es": "Acerca de", "en": "About"},
    "reports": {"es": "Informe", "en": "Report"},
    "privacy": {"es": "Privacidad", "en": "Privacy"},
    "privacy_deleted": {"es": "Cuenta eliminada", "en": "Account deleted"},
    "profile": {"es": "Perfil", "en": "Profile"},
    "login": {"es": "Iniciar sesión", "en": "Sign in"},
    "register": {"es": "Registro", "en": "Register"},
    "admin": {"es": "Administración", "en": "Administration"},
    "admin_imports": {"es": "Importaciones", "en": "Imports"},
    "upload": {"es": "Importar datos", "en": "Import data"},
}
_CANONICAL_PATHS: dict[str, RouteMatch] = {
    route.path(language): RouteMatch(route.route_id, language, route.path(language))
    for route in _ROUTE_DEFINITIONS
    for language in SUPPORTED_LANGUAGES
}

# Historical and mixed-language URLs are redirects, never additional canonical pages.
LEGACY_REDIRECTS: dict[str, str] = {
    "/": "/es",
    "/estadisticas": "/es/estadisticas",
    "/statistics": "/en/statistics",
    "/stadistics": "/en/statistics",
    "/tendencias": "/es/tendencias",
    "/trends": "/en/trends",
    "/espana": "/es/espana",
    "/spain": "/en/spain",
    "/didactica": "/es/didactica",
    "/didactics": "/en/learning",
    "/learning": "/en/learning",
    "/es/didactics": "/es/didactica",
    "/en/didactics": "/en/learning",
    "/didactica/diccionario": "/es/didactica/diccionario",
    "/didactica/presentaciones": "/es/didactica/presentaciones",
    "/didactica/juegos": "/es/didactica/juegos",
    "/didactica/juegos/sopa-de-letras": "/es/didactica/juegos/sopa-de-letras",
    "/word-search": "/en/learning/games/word-search",
    "/didactica/docentes": "/es/didactica/docentes",
    "/didactica/profesores": "/es/didactica/docentes",
    "/didactica/docentes/crear": "/es/didactica/docentes/crear",
    "/didactica/docentes/actividad": "/es/didactica/docentes/actividad",
    "/didactica/progreso": "/es/didactica",
    "/es/didactica/progreso": "/es/didactica",
    "/en/learning/progress": "/en/learning",
    "/about": "/en/about",
    "/acerca-de": "/es/acerca-de",
    "/informes": "/es/informe",
    "/report": "/en/report",
    "/reports": "/en/report",
    "/es/reports": "/es/informe",
    "/en/reports": "/en/report",
    "/privacidad": "/es/privacidad",
    "/privacy": "/en/privacy",
    "/privacidad/cuenta-eliminada": "/es/privacidad/cuenta-eliminada",
    "/user": "/en/profile",
    "/perfil": "/es/perfil",
    "/es/user": "/es/perfil",
    "/en/user": "/en/profile",
    "/login": "/en/sign-in",
    "/iniciar-sesion": "/es/iniciar-sesion",
    "/es/login": "/es/iniciar-sesion",
    "/en/login": "/en/sign-in",
    "/register": "/en/register",
    "/registro": "/es/registro",
    "/admin": "/en/admin",
    "/admin/imports": "/en/admin/imports",
    "/administracion": "/es/administracion",
    "/administracion/importaciones": "/es/administracion/importaciones",
    "/upload": "/en/upload",
    "/importar": "/es/importar",
}

for route in _ROUTE_DEFINITIONS:
    es_suffix = route.es.removeprefix("/es")
    en_suffix = route.en.removeprefix("/en")
    if es_suffix and en_suffix:
        mixed_es = f"/es{en_suffix}"
        mixed_en = f"/en{es_suffix}"
        if mixed_es != route.es:
            LEGACY_REDIRECTS.setdefault(mixed_es, route.es)
        if mixed_en != route.en:
            LEGACY_REDIRECTS.setdefault(mixed_en, route.en)

PUBLIC_PAGE_PATHS = frozenset((*_CANONICAL_PATHS, *LEGACY_REDIRECTS))
SAFE_NEXT_PATHS = frozenset(_CANONICAL_PATHS)

_active_language: ContextVar[Language] = ContextVar(
    "rainbowlens_route_language", default=DEFAULT_LANGUAGE
)


def normalize_language(language: str | None) -> Language:
    return "en" if language == "en" else "es"


def current_route_language() -> Language:
    return _active_language.get()


@contextmanager
def localized_route_context(language: str | None) -> Iterator[None]:
    token = _active_language.set(normalize_language(language))
    try:
        yield
    finally:
        _active_language.reset(token)


def route_path(route_id: str, language: str | None = None) -> str:
    route = ROUTES[route_id]
    selected = normalize_language(language) if language is not None else current_route_language()
    return route.path(selected)


def match_route(pathname: str | None) -> RouteMatch | None:
    path = _normalized_path(pathname)
    exact = _CANONICAL_PATHS.get(path)
    if exact is not None:
        return exact
    for language in SUPPORTED_LANGUAGES:
        base = route_path("educator_public_activity", language)
        prefix = f"{base}/"
        if path.startswith(prefix):
            public_id = path.removeprefix(prefix)
            if public_id and "/" not in public_id:
                return RouteMatch("educator_public_activity", language, path, public_id)
    return None


def legacy_redirect_target(pathname: str | None) -> str | None:
    path = _normalized_path(pathname)
    return LEGACY_REDIRECTS.get(path)


def language_from_path(pathname: str | None, fallback: str | None = None) -> Language:
    path = _normalized_path(pathname)
    if path == "/en" or path.startswith("/en/"):
        return "en"
    if path == "/es" or path.startswith("/es/"):
        return "es"
    target = LEGACY_REDIRECTS.get(path)
    if target:
        return language_from_path(target)
    return normalize_language(fallback)


def equivalent_path(pathname: str | None, language: str) -> str | None:
    match = match_route(pathname)
    if match is None:
        target = legacy_redirect_target(pathname)
        match = match_route(target)
    if match is None:
        return None
    target = route_path(match.route_id, language)
    return f"{target}/{match.public_id}" if match.public_id else target


def client_route_config() -> dict[str, object]:
    return {
        "defaultLanguage": DEFAULT_LANGUAGE,
        "routes": {
            route.route_id: {"es": route.es, "en": route.en} for route in _ROUTE_DEFINITIONS
        },
        "pathIndex": {path: match.route_id for path, match in _CANONICAL_PATHS.items()},
        "titles": ROUTE_TITLES,
        "dynamicRouteIds": ["educator_public_activity"],
    }


def is_safe_next(value: str | None) -> bool:
    return canonical_safe_next(value) is not None


def canonical_safe_next(value: str | None) -> str | None:
    if not value or "\\" in value:
        return None
    parsed = urlsplit(value)
    decoded_path = unquote(parsed.path)
    if parsed.scheme or parsed.netloc or parsed.fragment or decoded_path.startswith("//"):
        return None
    target = parsed.path if parsed.path in SAFE_NEXT_PATHS else LEGACY_REDIRECTS.get(parsed.path)
    if target not in SAFE_NEXT_PATHS:
        return None
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{target}{query}"


def _normalized_path(pathname: str | None) -> str:
    path = pathname or "/"
    if path != "/":
        path = path.rstrip("/")
    return path or "/"
