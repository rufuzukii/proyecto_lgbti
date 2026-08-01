from app.edu.lesson_service import list_lessons


def list_learning_units() -> list[dict]:
    """Return lightweight metadata; full slides stay in the lesson service."""
    return [
        {
            "id": lesson.id,
            "title": {"es": lesson.title.es, "en": lesson.title.en},
            "description": {"es": lesson.description.es, "en": lesson.description.en},
            "duration_minutes": lesson.duration_minutes,
        }
        for lesson in list_lessons()
    ]
