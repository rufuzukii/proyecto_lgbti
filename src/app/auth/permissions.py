from enum import Enum

from app.users.schemas import UserRole, UserType


class Permission(str, Enum):
    VIEW_DASHBOARD = "view_dashboard"
    MANAGE_USERS = "manage_users"
    EXPORT_DATA = "export_data"
    EXPORT_CHARTS = "export_charts"
    GENERATE_REPORTS = "generate_reports"
    ACCESS_EDU = "access_edu"


ROLE_PERMISSIONS = {
    UserRole.ADMIN: {
        Permission.VIEW_DASHBOARD,
        Permission.MANAGE_USERS,
        Permission.EXPORT_DATA,
        Permission.EXPORT_CHARTS,
        Permission.GENERATE_REPORTS,
        Permission.ACCESS_EDU,
    },
    UserRole.COMMON: {
        Permission.VIEW_DASHBOARD,
        Permission.EXPORT_DATA,
        Permission.EXPORT_CHARTS,
        Permission.GENERATE_REPORTS,
        Permission.ACCESS_EDU,
    },
    UserRole.ANONYMOUS: {Permission.ACCESS_EDU},
}


def has_permission(role: UserRole, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, set())


def is_admin_user(user: object) -> bool:
    role = getattr(user, "role", None)
    role_value = role.value if isinstance(role, UserRole) else str(role or "")
    return role_value.lower() == UserRole.ADMIN.value


def can_access_user_type(role: UserRole, user_type: UserType | None) -> bool:
    if role == UserRole.ADMIN:
        return True
    if role == UserRole.COMMON:
        return user_type in {UserType.RRHH, UserType.PROFESOR, UserType.COMUN}
    return False

