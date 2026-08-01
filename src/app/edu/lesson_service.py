from __future__ import annotations

from functools import lru_cache

from app.edu.models import Lesson
from app.edu.repository import load_json


@lru_cache(maxsize=1)
def list_lessons() -> tuple[Lesson, ...]:
    return tuple(Lesson.from_mapping(item) for item in load_json("lessons"))


def get_lesson(lesson_id: str) -> Lesson | None:
    return next((lesson for lesson in list_lessons() if lesson.id == lesson_id), None)
