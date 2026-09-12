from types import SimpleNamespace

import pytest

from app.modules.account.users.schemas import UserRole, UserType
from app.modules.didactics import custom_game_service
from app.modules.didactics.glossary_service import list_glossary_terms


class Collection:
    def __init__(self):
        self.documents: list[dict] = []
        self.find_calls = 0
        self.last_delete_query = None

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
        self.last_delete_query = dict(query)
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
            "term_ids": term_ids,
            "question_count": 5,
            "shuffle": True,
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
    assert stored["public_id"] == saved["public_id"]
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
    assert collection.last_delete_query == {
        "id": duplicate["id"],
        "owner_user_id": "docente-1",
    }
    assert custom_game_service.get_owned_game(owner, duplicate["id"]) is None

    english_copy = custom_game_service.duplicate_owned_game(owner, saved["id"], language="en")
    assert english_copy["title"].endswith("(copy)")
    assert english_copy["configuration"] == saved["configuration"]


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
    assert custom_game_service.delete_owned_game(admin, saved["id"]) is True
    assert collection.last_delete_query == {"id": saved["id"]}
    assert custom_game_service.get_owned_game(admin, saved["id"]) is None


def test_public_id_loads_game_without_exposing_owner(monkeypatch) -> None:
    collection = Collection()
    monkeypatch.setattr(custom_game_service, "get_mongo_collection", lambda _name: collection)
    saved = custom_game_service.save_owned_game(_user("docente-1"), None, _guess_values())

    public = custom_game_service.get_public_game(saved["public_id"])

    assert public is not None
    assert public["id"] == saved["id"]
    assert "owner_user_id" not in public
    assert custom_game_service.get_public_game("missing-share-id") is None


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


def test_word_search_uses_glossary_ids_and_calculates_board_size() -> None:
    fitting = [
        term.id
        for term in list_glossary_terms()
        if term.word_search_enabled("es")
        and 1 <= len(custom_game_service.normalize_word_search_term(term.term)) <= 10
    ][:6]
    activity = custom_game_service.validate_activity(
        {
            "game_type": "word_search",
            "title": "Identidades",
            "language": "es",
            "configuration": {
                "term_ids": fitting,
            },
        }
    )
    state = custom_game_service.build_activity_game_state(activity, seed=42)
    assert {word["id"] for word in state["words"]} <= set(fitting)
    assert 10 <= state["rows"] <= 15
    assert len(state["words"]) == 6


def test_word_search_activity_can_be_saved_and_rebuilt(monkeypatch) -> None:
    collection = Collection()
    monkeypatch.setattr(custom_game_service, "get_mongo_collection", lambda _name: collection)
    owner = _user("docente-1")
    term_ids = [
        term.id
        for term in list_glossary_terms()
        if term.word_search_enabled("es")
        and len(custom_game_service.normalize_word_search_term(term.term)) <= 12
    ][:6]
    values = {
        "game_type": "word_search",
        "title": "Conceptos de identidad",
        "language": "es",
        "status": "ACTIVE",
        "configuration": {"term_ids": term_ids},
    }

    saved = custom_game_service.save_owned_game(owner, None, values)
    loaded = custom_game_service.get_owned_game(owner, saved["id"])
    assert loaded is not None
    state = custom_game_service.build_activity_game_state(loaded, seed=9)
    assert len(state["words"]) == 6
    assert all(word["direction"] != "left" for word in state["words"])


def test_english_teacher_word_search_uses_english_terms() -> None:
    term_ids = [
        term.id
        for term in list_glossary_terms()
        if term.word_search_enabled("en")
        and len(custom_game_service.normalize_word_search_term(term.term_en)) <= 10
    ][:6]
    activity = custom_game_service.validate_activity(
        {
            "game_type": "word_search",
            "title": "Identity concepts",
            "language": "en",
            "configuration": {"term_ids": term_ids},
        }
    )

    state = custom_game_service.build_activity_game_state(activity, seed=17)
    expected = {term.localized_term("en") for term in list_glossary_terms() if term.id in term_ids}
    assert {word["display"] for word in state["words"]} == expected


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
                "country_codes": ["ES", "PT", "DE", "PL", "IT"],
                "year": 2026,
            },
        }
    )
    assert activity["configuration"]["source_dataset_version"] == "ilga-2026"
    assert "PL" in activity["configuration"]["country_codes"]

    collection = Collection()
    monkeypatch.setattr(custom_game_service, "get_mongo_collection", lambda _name: collection)
    saved = custom_game_service.save_owned_game(_user("docente-1"), None, activity)
    loaded = custom_game_service.get_owned_game(_user("docente-1"), saved["id"])
    assert loaded is not None
    assert loaded["configuration"]["country_codes"] == ["ES", "PT", "DE", "PL", "IT"]


def test_non_docente_cannot_call_service_directly(monkeypatch) -> None:
    monkeypatch.setattr(custom_game_service, "get_mongo_collection", lambda _name: Collection())
    with pytest.raises(custom_game_service.CustomGameAuthorizationError):
        custom_game_service.list_owned_games(_user("common-1", UserType.COMUN))
