from enum import StrEnum

from app.users.schemas import UserRole, UserType


class Permission(StrEnum):
    VIEW_PUBLIC_CONTENT = "view_public_content"
    VIEW_DASHBOARD = "view_dashboard"
    MANAGE_USERS = "manage_users"
    EXPORT_DATA = "export_data"
    EXPORT_CHARTS = "export_charts"
    UPLOAD_DATA = "upload_data"
    GENERATE_REPORTS = "generate_reports"
    CONFIGURE_ADVANCED_REPORTS = "configure_advanced_reports"
    ACCESS_EDU = "access_edu"
    PLAY_EDU_GAMES = "play_edu_games"
    ACCESS_DOCENTE_RESOURCES = "access_docente_resources"
    MANAGE_OWN_EDU_GAMES = "manage_own_edu_games"


ROLE_PERMISSIONS = {
    UserRole.COMMON: {
        Permission.VIEW_PUBLIC_CONTENT,
        Permission.VIEW_DASHBOARD,
        Permission.EXPORT_DATA,
        Permission.EXPORT_CHARTS,
        Permission.GENERATE_REPORTS,
        Permission.ACCESS_EDU,
        Permission.PLAY_EDU_GAMES,
    },
    UserRole.ANONYMOUS: {
        Permission.VIEW_PUBLIC_CONTENT,
        Permission.ACCESS_EDU,
    },
}

USER_TYPE_PERMISSIONS = {
    UserType.RRHH: {Permission.CONFIGURE_ADVANCED_REPORTS},
    UserType.POLITICO: {Permission.CONFIGURE_ADVANCED_REPORTS},
    UserType.ONG: {Permission.CONFIGURE_ADVANCED_REPORTS},
    UserType.DOCENTE: {
        Permission.ACCESS_DOCENTE_RESOURCES,
        Permission.MANAGE_OWN_EDU_GAMES,
    },
    UserType.COMUN: set(),
}


def has_permission(
    role: UserRole,
    permission: Permission,
    user_type: UserType | None = None,
) -> bool:
    if role == UserRole.ADMIN:
        return True
    type_permissions = (
        USER_TYPE_PERMISSIONS.get(user_type, set()) if user_type is not None else set()
    )
    return permission in ROLE_PERMISSIONS.get(role, set()) or permission in type_permissions


def user_has_permission(user: object, permission: Permission) -> bool:
    authenticated = bool(getattr(user, "is_authenticated", False))
    role = getattr(user, "role", None) if authenticated else UserRole.ANONYMOUS
    if isinstance(role, UserRole):
        resolved = role
    else:
        try:
            resolved = UserRole(str(role or "").lower())
        except ValueError:
            return False
    return has_permission(
        resolved,
        permission,
        _resolved_user_type(user) if authenticated else None,
    )


def is_admin_user(user: object) -> bool:
    if not bool(getattr(user, "is_authenticated", False)):
        return False
    role = getattr(user, "role", None)
    role_value = role.value if isinstance(role, UserRole) else str(role or "")
    return role_value.lower() == UserRole.ADMIN.value


def can_access_user_type(role: UserRole, user_type: UserType | None) -> bool:
    if role == UserRole.ADMIN:
        return True
    if role == UserRole.COMMON:
        return user_type in set(UserType)
    return False


def can_access_docente_material(user: object) -> bool:
    return user_has_permission(user, Permission.ACCESS_DOCENTE_RESOURCES)


def can_manage_own_edu_games(user: object) -> bool:
    return user_has_permission(user, Permission.MANAGE_OWN_EDU_GAMES)


def can_configure_advanced_reports(user: object) -> bool:
    return user_has_permission(user, Permission.CONFIGURE_ADVANCED_REPORTS)


def _resolved_user_type(user: object) -> UserType | None:
    value = getattr(user, "user_type", None)
    if isinstance(value, UserType):
        return value
    try:
        clean_value = str(value or "").strip().casefold()
        if clean_value == "profesor":
            clean_value = UserType.DOCENTE.value
        return UserType(clean_value)
    except ValueError:
        return None
