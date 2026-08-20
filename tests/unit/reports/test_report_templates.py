from types import SimpleNamespace

import pytest

from app.reports.templates import (
    PROFILE_TEMPLATES,
    REPORT_PROFILES,
    apply_template_defaults,
    find_report_template,
    report_profile_key,
    report_templates_for_user,
)
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


@pytest.mark.parametrize(
    ("user", "expected_profile"),
    [
        (_user(authenticated=False, user_type=None), "anonymous"),
        (_user(user_type=UserType.COMUN), "comun"),
        (_user(user_type=UserType.RRHH), "rrhh"),
        (_user(user_type=UserType.DOCENTE), "docente"),
        (_user(user_type=UserType.POLITICO), "politico"),
        (_user(user_type=UserType.SOCIOLOGO), "sociologo"),
        (_user(user_type=UserType.ONG), "ong"),
        (_user(role=UserRole.ADMIN, user_type=UserType.ADMIN), "admin"),
    ],
)
def test_each_profile_resolves_its_own_templates(user, expected_profile: str) -> None:
    # Arrange / Act
    templates = report_templates_for_user(user)

    # Assert
    assert report_profile_key(user) == expected_profile
    expected_count = sum(
        len(values) for key, values in PROFILE_TEMPLATES.items() if key != "anonymous"
    ) if expected_profile == "admin" else 2
    assert len(templates) == expected_count
    assert len({template.id for template in templates}) == expected_count
    assert all(template.name_es and template.name_en for template in templates)
    assert all(template.description_es and template.description_en for template in templates)


def test_profile_template_ids_do_not_overlap() -> None:
    identifiers = [
        template.id for templates in PROFILE_TEMPLATES.values() for template in templates
    ]

    # Assert
    assert len(identifiers) == len(set(identifiers))


def test_every_report_profile_has_meaningful_objectives_and_output_rules() -> None:
    assert set(REPORT_PROFILES) == {
        "anonymous", "comun", "docente", "rrhh", "ong", "politico", "sociologo", "admin"
    }
    for profile in REPORT_PROFILES.values():
        assert len(profile.objectives) >= 2
        assert profile.recommended_sections
        assert profile.recommended_charts


def test_template_defaults_preserve_an_inherited_statistics_selection() -> None:
    # Arrange
    user = _user(user_type=UserType.POLITICO)
    template = find_report_template(user, "policy_legal_brief")
    inherited = {"source": "fra", "indicator_id": "D1_1", "countries": ["ES"]}

    # Act
    values = apply_template_defaults(inherited, template, language="es")

    # Assert
    assert values["source"] == "fra"
    assert values["indicator_id"] == "D1_1"
    assert values["countries"] == ["ES"]
    assert values["template_id"] == "policy_legal_brief"
    assert values["title"] == template.title_es


def test_unknown_template_falls_back_within_the_current_profile() -> None:
    # Arrange
    user = _user(user_type=UserType.SOCIOLOGO)

    # Act
    selected = find_report_template(user, "rrhh_workplace_diagnostic")

    # Assert
    assert selected.id == "sociology_cross_section"
