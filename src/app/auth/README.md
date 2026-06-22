# Autenticación y autorización

## Archivos Python

### `app.py`

Implementa un servicio Flask JSON independiente:

- `AuthUser`: adaptación de usuario para Flask-Login.
- `create_auth_app()`: configura cookies, Flask-Login y rutas.
- `POST /auth/register`: valida con Pydantic y crea un usuario común.
- `POST /auth/login`: autentica contraseña y abre sesión.
- `POST /auth/logout`: cierra una sesión autenticada.
- `GET /auth/me`: devuelve rol anónimo o usuario actual.
- `_rate_key()`: normaliza IP y email para el limitador.

Este servicio se ejecuta con `run_auth.py`. Es independiente de las rutas HTML registradas dentro de `dash_app.py`.

### `rate_limit.py`

Define un limitador compartido por el servicio Flask y las rutas HTML de Dash. Usa Redis cuando existe `RATE_LIMIT_REDIS_URL` o `REDIS_URL`, de modo que varios workers comparten estado. Si Redis no está configurado o no responde, usa un fallback local en memoria para desarrollo.

### `csrf.py`

Genera un token aleatorio por sesión y lo valida mediante comparación constante. Protege los formularios POST de Dash.

### `permissions.py`

Declara permisos por rol y una regla de acceso por `UserType`. La interfaz actual usa comprobaciones directas de rol para administración; esta matriz todavía no gobierna todas las rutas.

### `__init__.py`

Marcador de paquete sin código.
