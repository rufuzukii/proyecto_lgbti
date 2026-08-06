# Usuarios

Este paquete modela usuarios y centraliza las operaciones PostgreSQL.

## `schemas.py`

- `UserRole`: `anonymous`, `admin` y `common`.
- `UserType`: `comun`, `admin`, `docente`, `rrhh`, `politico`, `ong` y `sociologo`.
- `UserRegister`: valida nombre, email, contraseña, organización y tipo.
- `UserRead`: respuesta pública sin hash de contraseña.

## `service.py`

- `UserStorageError`: error previsto para problemas de almacenamiento seguro.
- `UserRecord`: modelo interno con `password_hash`.
- `list_users()`, `get_user()`, `get_user_record()` y `get_user_record_by_email()`: consultas.
- `create_user()`: normaliza email, genera hash Werkzeug e inserta el tipo común salvo alta administrativa explícita.
- `authenticate_user()`: comprueba el hash.
- `update_user_profile()`: exige contraseña actual y permite cambiar nombre, email y contraseña.
- `update_user_as_admin()`: permite cambiar nombre, email, organización y tipo de usuario.
- `delete_user_as_admin()`: elimina por UUID.
- Helpers privados: conexión, DSN, normalización, conversión de filas y derivación del rol técnico desde `user_type`.

`DATABASE_URL` tiene prioridad. Si no existe, el servicio compone el DSN desde `config.py`.
Los perfiles funcionales se persisten exclusivamente en `user_type`. El rol técnico
`admin`/`common` se deriva en Python: `user_type = 'admin'` concede el rol administrativo
y cualquier otro tipo concede el rol común. El servicio presupone que la tabla PostgreSQL
ya existe y no ejecuta DDL ni migraciones.

## `__init__.py`

Marcador de paquete sin exportaciones.
