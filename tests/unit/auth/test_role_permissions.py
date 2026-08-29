from types import SimpleNamespace

from app.core.auth.permissions import Permission, user_has_permission
from app.modules.account.users.schemas import UserRole, UserType


def _user(
    *,
    authenticated: bool = True,
    role: UserRole = UserRole.COMMON,
    user_type: UserType | None = UserType.COMUN,
):
    return SimpleNamespace(
        is_authenticated=authenticated,
        role=role,
        user_type=user_type,
    )


def test_anonymous_users_receive_all_public_tool_permissions() -> None:
    user = _user(authenticated=False, user_type=UserType.DOCENTE)

    assert user_has_permission(user, Permission.VIEW_PUBLIC_CONTENT)
    assert user_has_permission(user, Permission.ACCESS_EDU)
    assert user_has_permission(user, Permission.PLAY_EDU_GAMES)
    assert user_has_permission(user, Permission.GENERATE_REPORTS)
    assert user_has_permission(user, Permission.EXPORT_DATA)
    assert user_has_permission(user, Permission.EXPORT_CHARTS)
    assert not user_has_permission(user, Permission.ACCESS_DOCENTE_RESOURCES)
    assert not user_has_permission(user, Permission.UPLOAD_DATA)
    assert not user_has_permission(user, Permission.MANAGE_OWN_EDU_GAMES)


def test_common_user_receives_public_tools_but_not_management_permissions() -> None:
    user = _user()

    assert user_has_permission(user, Permission.VIEW_DASHBOARD)
    assert user_has_permission(user, Permission.PLAY_EDU_GAMES)
    assert user_has_permission(user, Permission.GENERATE_REPORTS)
    assert not user_has_permission(user, Permission.UPLOAD_DATA)
    assert not user_has_permission(user, Permission.ACCESS_DOCENTE_RESOURCES)

    sociologist = _user(user_type=UserType.SOCIOLOGO)
    assert user_has_permission(sociologist, Permission.VIEW_DASHBOARD)
    assert user_has_permission(sociologist, Permission.UPLOAD_DATA)


def test_professional_profiles_can_import_and_docente_keeps_educational_permissions() -> None:
    for profile in (UserType.RRHH, UserType.POLITICO, UserType.ONG, UserType.SOCIOLOGO):
        user = _user(user_type=profile)
        assert user_has_permission(user, Permission.GENERATE_REPORTS)
        assert user_has_permission(user, Permission.UPLOAD_DATA)
        assert not user_has_permission(user, Permission.ACCESS_DOCENTE_RESOURCES)
        assert not user_has_permission(user, Permission.MANAGE_OWN_EDU_GAMES)

    docente = _user(user_type=UserType.DOCENTE)
    assert user_has_permission(docente, Permission.ACCESS_DOCENTE_RESOURCES)
    assert user_has_permission(docente, Permission.MANAGE_OWN_EDU_GAMES)
    assert not user_has_permission(docente, Permission.UPLOAD_DATA)


def test_admin_automatically_inherits_every_current_and_future_permission() -> None:
    admin = _user(role=UserRole.ADMIN, user_type=None)

    assert all(user_has_permission(admin, permission) for permission in Permission)
