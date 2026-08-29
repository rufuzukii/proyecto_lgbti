from __future__ import annotations

from app.modules.account.users.schemas import UserRole, UserType
from app.shared.data.taxonomy import taxonomy_label


def role_label(
    role: UserRole | str,
    user_type: UserType | str | None = None,
    *,
    language: str = "es",
) -> str:
    value = role.value if isinstance(role, UserRole) else str(role)
    if value == UserRole.ADMIN.value:
        return taxonomy_label("role", UserType.ADMIN.value, language)
    profile = user_type_value(user_type) or UserType.COMUN.value
    return taxonomy_label("role", profile, language)


def user_type_value(user_type: UserType | str | None) -> str:
    value = user_type.value if isinstance(user_type, UserType) else str(user_type or "")
    return UserType.DOCENTE.value if value == "profesor" else value
