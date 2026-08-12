# Contenido didáctico

Este paquete contiene la capa de dominio y servicios de `/didactica`:

- `data/`: glosario, lecciones y recursos docentes JSON versionados.
- `repository.py`: lectura validada y cacheada de datos estáticos.
- `glossary_service.py`, `lesson_service.py`, `game_service.py` y `word_search_service.py`:
  consultas y juegos públicos. Los tres juegos de vocabulario se construyen desde el mismo
  catálogo cacheado del glosario, sin duplicarlo. La sopa de letras conserva su partida únicamente
  en memoria del navegador y no necesita autenticación.
- `teacher_service.py`: metadatos docentes y PDF generado en memoria.
- `custom_game_service.py`: juegos propios de cada Docente, validados y persistidos en MongoDB.
- `progress_service.py`: progreso resumido por usuario en MongoDB.
- `translations.py`: vocabulario común español/inglés.
- `content.py`: metadatos ligeros utilizados por `/edu/units`.

El contenido completo se carga al abrir un recurso; el índice y la API de unidades
solo exponen metadatos ligeros.
