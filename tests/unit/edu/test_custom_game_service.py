from types import SimpleNamespace

import pytest

from app.edu import custom_game_service
from app.users.schemas import UserRole, UserType


class Collection:
    def __init__(self):
        self.documents: list[dict] = []

    def find(self, query, _projection):
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
        document.update(update["$set"])

    def delete_one(self, query):
        before = len(self.documents)
        self.documents = [item for item in self.documents if not _matches(item, query)]
        return SimpleNamespace(deleted_count=before - len(self.documents))


def _matches(document, query):
    for key, expected in query.items():
        if isinstance(expected, dict) and "$ne" in expected:
            if document.get(key) == expected["$ne"]:
                return False
        elif document.get(key) != expected:
            return False
    return True


def _user(identifier: str, profile: UserType = UserType.DOCENTE):
    return SimpleNamespace(
        is_authenticated=True,
        role=UserRole.COMMON,
        user_type=profile,
        get_id=lambda: identifier,
    )


def _values():
    return {
        "game_type": "multiple_choice",
        "title_es": "Conceptos básicos",
        "title_en": "Basic concepts",
        "prompt_es": "¿Qué significa identidad?",
        "prompt_en": "What does identity mean?",
        "answer_es": "Respuesta correcta",
        "answer_en": "Correct answer",
        "distractors_es": "Opción uno\nOpción dos",
        "distractors_en": "Option one\nOption two",
        "explanation_es": "Explicación <script>no</script>",
        "explanation_en": "Explanation",
    }


def test_docente_can_create_edit_list_and_delete_only_owned_games(monkeypatch) -> None:
    collection = Collection()
    monkeypatch.setattr(custom_game_service, "get_mongo_collection", lambda _name: collection)
    owner = _user("docente-1")

    saved = custom_game_service.save_owned_game(owner, None, _values())
    assert custom_game_service.get_owned_game(owner, saved["id"])["title_es"] == "Conceptos básicos"
    assert "<script>" not in custom_game_service.get_owned_game(owner, saved["id"])["explanation_es"]
    assert [item["id"] for item in custom_game_service.list_owned_games(owner)] == [saved["id"]]
    assert custom_game_service.get_owned_game(_user("docente-2"), saved["id"]) is None

    changed = {**_values(), "title_es": "Título actualizado"}
    custom_game_service.save_owned_game(owner, saved["id"], changed)
    assert custom_game_service.get_owned_game(owner, saved["id"])["title_es"] == "Título actualizado"
    assert custom_game_service.delete_owned_game(owner, saved["id"])
    assert custom_game_service.list_owned_games(owner) == []


def test_non_docente_cannot_call_custom_game_service_directly(monkeypatch) -> None:
    monkeypatch.setattr(custom_game_service, "get_mongo_collection", lambda _name: Collection())

    with pytest.raises(custom_game_service.CustomGameAuthorizationError):
        custom_game_service.list_owned_games(_user("common-1", UserType.COMUN))
