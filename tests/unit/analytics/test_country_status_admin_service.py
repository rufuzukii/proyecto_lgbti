from unittest.mock import patch

import pytest

from app.modules.account.users.schemas import UserRole
from app.modules.home.country_status_admin_service import (
    CountryStatusAuthorizationError,
    CountryStatusValidationError,
    delete_country_lgbti_status,
    save_country_lgbti_status,
    validate_country_lgbti_status_payload,
)


class User:
    def __init__(self, role, *, is_authenticated=True):
        self.role = role
        self.is_authenticated = is_authenticated


def _payload(**overrides):
    payload = {
        "country": "Spain",
        "country_code": "ES",
        "year": 2026,
        "title": "Situacion general",
        "summary": "Texto manual validado suficientemente largo para poder guardar el registro.",
        "legal_context": "Contexto legal",
        "social_context": "Contexto social",
        "positive_developments": "Avance 1\nAvance 2",
        "main_challenges": "Reto 1",
        "source_name": "ILGA-Europe Annual Review 2026",
        "source_url": "https://www.ilga-europe.org/files/uploads/2026/02/2026-ILGA-EUROPE-ANNUAL-REVIEW.pdf",
        "reviewed_at": "2026-03-15",
        "observations": "Revision manual",
        "active": True,
    }
    payload.update(overrides)
    return payload


def test_validate_country_status_payload_normalizes_fields() -> None:
    record = validate_country_lgbti_status_payload(_payload(country_code="es"))

    assert record["dataset"] == "country_lgbti_status"
    assert record["country_code"] == "ES"
    assert record["positive_developments"] == ["Avance 1", "Avance 2"]


def test_validate_country_status_payload_rejects_invalid_fields() -> None:
    with pytest.raises(CountryStatusValidationError) as exc_info:
        validate_country_lgbti_status_payload(
            _payload(country="", year=1800, source_url="javascript:alert(1)", summary="Corto")
        )

    assert set(exc_info.value.field_errors) >= {"country", "year", "source_url", "summary"}


def test_non_admin_cannot_save_country_status() -> None:
    with pytest.raises(CountryStatusAuthorizationError):
        save_country_lgbti_status(_payload(), user=User(UserRole.COMMON), mode="edit")


def test_admin_can_create_country_status_record() -> None:
    with (
        patch(
            "app.modules.home.country_status_admin_service.get_country_lgbti_status_record",
            return_value=None,
        ),
        patch(
            "app.modules.home.country_status_admin_service.upsert_country_lgbti_status_record"
        ) as upsert,
        patch("app.modules.home.country_status_admin_service.invalidate_analytics_cache"),
    ):
        saved = save_country_lgbti_status(_payload(), user=User(UserRole.ADMIN), mode="create")

    assert saved["country_code"] == "ES"
    upsert.assert_called_once()


def test_create_rejects_duplicate_country_year() -> None:
    with (
        patch(
            "app.modules.home.country_status_admin_service.get_country_lgbti_status_record",
            return_value={"country_code": "ES", "year": 2026},
        ),
        pytest.raises(CountryStatusValidationError) as exc_info,
    ):
        save_country_lgbti_status(_payload(), user=User(UserRole.ADMIN), mode="create")

    assert "year" in exc_info.value.field_errors


def test_admin_can_edit_existing_country_status_record() -> None:
    with (
        patch(
            "app.modules.home.country_status_admin_service.get_country_lgbti_status_record",
            return_value={"country_code": "ES", "year": 2026},
        ),
        patch(
            "app.modules.home.country_status_admin_service.upsert_country_lgbti_status_record"
        ) as upsert,
        patch("app.modules.home.country_status_admin_service.invalidate_analytics_cache"),
    ):
        save_country_lgbti_status(_payload(), user=User(UserRole.ADMIN), mode="edit")

    upsert.assert_called_once()


def test_delete_requires_admin_and_confirmation() -> None:
    with pytest.raises(CountryStatusAuthorizationError):
        delete_country_lgbti_status("ES", 2026, user=User(UserRole.COMMON), confirmed=True)

    with pytest.raises(CountryStatusValidationError):
        delete_country_lgbti_status("ES", 2026, user=User(UserRole.ADMIN), confirmed=False)

    with pytest.raises(CountryStatusAuthorizationError):
        delete_country_lgbti_status(
            "ES",
            2026,
            user=User(UserRole.ADMIN, is_authenticated=False),
            confirmed=True,
        )


def test_admin_delete_deactivates_record() -> None:
    with (
        patch(
            "app.modules.home.country_status_admin_service.deactivate_country_lgbti_status_record"
        ) as deactivate,
        patch("app.modules.home.country_status_admin_service.invalidate_analytics_cache"),
    ):
        delete_country_lgbti_status("ES", 2026, user=User(UserRole.ADMIN), confirmed=True)

    deactivate.assert_called_once_with("ES", 2026)
