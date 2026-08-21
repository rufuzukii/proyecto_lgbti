from types import SimpleNamespace

import pytest

from app.edu import custom_game_service
from app.edu.glossary_service import list_glossary_terms
from app.users.schemas import UserRole, UserType


class Collection:
    def __init__(self):
        self.documents: list[dict] = []
        self.find_calls = 0

    def find(self, query, _projection):
        self.find_calls += 1
        return [document.copy() for document in self.documents if _matches(document, query)]

    def find_one(self, query, _projection=None):
        return next(
            (document.copy() for document in self.documents if _matches(document, query)),
            None,
        )

    def update_one(self, query, update, upsert=False):
        document = next((item for item in self.documents if _matches(item, query)), None)
        if document is None and upsert:
            document = {**query, **update.get("$setOnInsert", {})}
            self.documents.append(document)
        assert document is not None
        document.update(update["$set"])

    def delete_one(self, query):
        before = len(self.documents)
        self.documents = [item for item in self.documents if not _matches(item, query)]
        return SimpleNamespace(deleted_count=before - len(self.documents))


def _matches(document, query):
    return all(document.get(key) == expected for key, expected in query.items())


def _user(
    identifier: str,
    profile: UserType = UserType.DOCENTE,
    role: UserRole = UserRole.COMMON,
):
    return SimpleNamespace(
        is_authenticated=True,
        role=role,
        user_type=profile,
        get_id=lambda: identifier,
    )


def _guess_values():
    term_ids = [term.id for term in list_glossary_terms()[:5]]
    return {
        "game_type": "guess_term",
        "title": "Conceptos <script>básicos</script>",
        "description": "Diversidad para el aula",
        "instructions": "Relaciona cada definición.",
        "teacher_note": "Repasar antes la unidad 1.",
        "language": "es",
        "status": "ACTIVE",
        "configuration": {
            "selection_mode": "manual",
            "term_ids": term_ids,
            "question_count": 5,
            "shuffle": True,
            "show_explanation": True,
        },
    }


def test_docente_crud_duplicate_and_owner_are_enforced(monkeypatch) -> None:
    collection = Collection()
    monkeypatch.setattr(custom_game_service, "get_mongo_collection", lambda _name: collection)
    owner = _user("docente-1")

    saved = custom_game_service.save_owned_game(owner, None, _guess_values())
    stored = custom_game_service.get_owned_game(owner, saved["id"])
    assert stored is not None
    assert stored["owner_user_id"] == "docente-1"
    assert "<script>" not in stored["title"]
    assert stored["configuration"]["term_ids"] == _guess_values()["configuration"]["term_ids"]
    assert "definition" not in str(stored["configuration"])

    with pytest.raises(custom_game_service.CustomGameAuthorizationError):
        custom_game_service.get_owned_game(_user("docente-2"), saved["id"])
    with pytest.raises(custom_game_service.CustomGameAuthorizationError):
        custom_game_service.save_owned_game(_user("docente-2"), saved["id"], _guess_values())
    with pytest.raises(custom_game_service.CustomGameAuthorizationError):
        custom_game_service.delete_owned_game(_user("docente-2"), saved["id"])

    duplicate = custom_game_service.duplicate_owned_game(owner, saved["id"])
    assert duplicate["id"] != saved["id"]
    assert duplicate["status"] == "DRAFT"
    assert duplicate["title"].endswith("(copia)")
    assert len(custom_game_service.list_owned_games(owner)) == 2
    assert collection.find_calls == 1

    assert custom_game_service.delete_owned_game(owner, duplicate["id"])


def test_admin_can_access_and_manage_another_owner_activity(monkeypatch) -> None:
    collection = Collection()
    monkeypatch.setattr(custom_game_service, "get_mongo_collection", lambda _name: collection)
    saved = custom_game_service.save_owned_game(_user("docente-1"), None, _guess_values())
    admin = _user("admin-1", UserType.ADMIN, UserRole.ADMIN)

    original = custom_game_service.get_owned_game(admin, saved["id"])
    assert original is not None
    assert original["owner_user_id"] == "docente-1"
    changed = {**_guess_values(), "title": "Revisada por administración"}
    custom_game_service.save_owned_game(admin, saved["id"], changed)
    updated = custom_game_service.get_owned_game(admin, saved["id"])
    assert updated is not None
    assert updated["title"] == changed["title"]
    assert len(custom_game_service.list_all_games(admin)) == 1


def test_only_three_real_game_types_are_accepted(monkeypatch) -> None:
    assert set(custom_game_service.GAME_TYPES) == {
        "guess_term",
        "word_search",
        "legal_ranking",
    }
    assert "multiple_choice" not in custom_game_service.GAME_TYPES
    invalid = {**_guess_values(), "game_type": "true_false"}
    with pytest.raises(custom_game_service.CustomGameValidationError, match="invalid_game_type"):
        custom_game_service.validate_activity(invalid)


def test_word_search_uses_glossary_ids_and_board_limits() -> None:
    fitting = [
        term.id
        for term in list_glossary_terms()
        if 1 <= len(custom_game_service.normalize_word_search_term(term.term)) <= 10
    ][:6]
    activity = custom_game_service.validate_activity(
        {
            "game_type": "word_search",
            "title": "Identidades",
            "language": "es",
            "configuration": {
                "selection_mode": "manual",
                "term_ids": fitting,
                "word_count": 6,
                "board_size": 10,
            },
        }
    )
    state = custom_game_service.build_activity_game_state(activity, seed=42)
    assert {word["id"] for word in state["words"]} <= set(fitting)
    assert state["rows"] == 10
    assert len(state["words"]) == 6


def test_ranking_validates_real_year_codes_zero_and_ties(monkeypatch) -> None:
    ranking = [
        SimpleNamespace(country_code="ES", score=80.0),
        SimpleNamespace(country_code="PT", score=70.0),
        SimpleNamespace(country_code="DE", score=70.0),
        SimpleNamespace(country_code="PL", score=0.0),
        SimpleNamespace(country_code="IT", score=20.0),
    ]
    monkeypatch.setattr(custom_game_service, "get_ilga_years", lambda: [2026])
    monkeypatch.setattr(custom_game_service, "get_ilga_document_by_year", lambda _year: {})
    monkeypatch.setattr(custom_game_service, "build_legal_ranking", lambda _document: ranking)
    activity = custom_game_service.validate_activity(
        {
            "game_type": "legal_ranking",
            "title": "Situación legal 2026",
            "language": "es",
            "configuration": {
                "selection_mode": "manual",
                "country_codes": ["ES", "PT", "DE", "PL", "IT"],
                "country_count": 5,
                "year": 2026,
            },
        }
    )
    assert activity["configuration"]["source_dataset_version"] == "ilga-2026"
    assert "PL" in activity["configuration"]["country_codes"]


def test_non_docente_cannot_call_service_directly(monkeypatch) -> None:
    monkeypatch.setattr(custom_game_service, "get_mongo_collection", lambda _name: Collection())
    with pytest.raises(custom_game_service.CustomGameAuthorizationError):
        custom_game_service.list_owned_games(_user("common-1", UserType.COMUN))
