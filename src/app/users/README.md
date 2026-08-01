# Usuarios

Este paquete modela usuarios y centraliza las operaciones PostgreSQL.

## `schemas.py`

- `UserRole`: `anonymous`, `admin` y `common`.
- `UserType`: `comun`, `docente`, `rrhh`, `politico` y `ong`.
- `UserRegister`: valida nombre, email, contraseña, organización y tipo.
- `UserRead`: respuesta pública sin hash de contraseña.

## `service.py`

- `UserStorageError`: error previsto para problemas de almacenamiento seguro.
- `UserRecord`: modelo interno con `password_hash`.
- `list_users()`, `get_user()`, `get_user_record()` y `get_user_record_by_email()`: consultas.
- `create_user()`: normaliza email, genera hash Werkzeug e inserta rol común salvo alta administrativa explícita.
- `authenticate_user()`: comprueba el hash.
- `update_user_profile()`: exige contraseña actual y permite cambiar nombre, email y contraseña.
- `update_user_as_admin()`: permite cambiar nombre, email, organización y rol.
- `delete_user_as_admin()`: elimina por UUID.
- `migrate_legacy_user_types()`: migra de forma idempotente el antiguo perfil educativo.
- Helpers privados: conexión, DSN, normalización, conversión de filas y compatibilidad de roles antiguos (`comun`/`user`).

`DATABASE_URL` tiene prioridad. Si no existe, el servicio compone el DSN desde `config.py`.
Los perfiles funcionales se persisten en `user_type` cuando la columna existe o,
por compatibilidad con el esquema desplegado, en `role`.

## `__init__.py`

Marcador de paquete sin exportaciones.
