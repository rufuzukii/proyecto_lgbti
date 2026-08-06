from types import SimpleNamespace

from app.auth.permissions import Permission, user_has_permission
from app.users.schemas import UserRole, UserType


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


def test_anonymous_users_only_receive_public_permissions() -> None:
    user = _user(authenticated=False, user_type=UserType.DOCENTE)

    assert user_has_permission(user, Permission.VIEW_PUBLIC_CONTENT)
    assert user_has_permission(user, Permission.ACCESS_EDU)
    assert not user_has_permission(user, Permission.PLAY_EDU_GAMES)
    assert not user_has_permission(user, Permission.GENERATE_REPORTS)
    assert not user_has_permission(user, Permission.UPLOAD_DATA)
    assert not user_has_permission(user, Permission.ACCESS_DOCENTE_RESOURCES)


def test_common_user_receives_general_features_but_not_privileged_tools() -> None:
    user = _user()

    assert user_has_permission(user, Permission.VIEW_DASHBOARD)
    assert user_has_permission(user, Permission.PLAY_EDU_GAMES)
    assert user_has_permission(user, Permission.GENERATE_REPORTS)
    assert not user_has_permission(user, Permission.UPLOAD_DATA)
    assert not user_has_permission(user, Permission.CONFIGURE_ADVANCED_REPORTS)

    sociologist = _user(user_type=UserType.SOCIOLOGO)
    assert user_has_permission(sociologist, Permission.VIEW_DASHBOARD)
    assert not user_has_permission(sociologist, Permission.UPLOAD_DATA)


def test_functional_profiles_receive_only_their_added_value() -> None:
    for profile in (UserType.RRHH, UserType.POLITICO, UserType.ONG):
        user = _user(user_type=profile)
        assert user_has_permission(user, Permission.CONFIGURE_ADVANCED_REPORTS)
        assert not user_has_permission(user, Permission.UPLOAD_DATA)
        assert not user_has_permission(user, Permission.ACCESS_DOCENTE_RESOURCES)

    docente = _user(user_type=UserType.DOCENTE)
    assert user_has_permission(docente, Permission.ACCESS_DOCENTE_RESOURCES)
    assert user_has_permission(docente, Permission.MANAGE_OWN_EDU_GAMES)
    assert not user_has_permission(docente, Permission.UPLOAD_DATA)
    assert not user_has_permission(docente, Permission.CONFIGURE_ADVANCED_REPORTS)


def test_admin_automatically_inherits_every_current_and_future_permission() -> None:
    admin = _user(role=UserRole.ADMIN, user_type=None)

    assert all(user_has_permission(admin, permission) for permission in Permission)
