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

Las sesiones autenticadas son permanentes con vencimiento deslizante: cada petición activa renueva el plazo configurado. La protección `strong` de Flask-Login se mantiene, pero un cambio del identificador de red observado a través del proxy deja la sesión como no reciente en vez de eliminar al usuario durante la navegación.

La factoría `create_auth_app()` permite ejecutar este servicio de forma independiente cuando sea
necesario. Las rutas HTML de producción siguen registradas dentro de `dash_app.py`.

### `rate_limit.py`

Define un limitador local acotado que comparten el servicio Flask y las rutas HTML de Dash dentro de cada worker. Las claves caducan por ventana temporal y el número de identidades retenidas se limita mediante `RATE_LIMIT_LOCAL_MAX_KEYS`.

### `csrf.py`

Genera un token aleatorio por sesión y lo valida mediante comparación constante. Protege los formularios POST de Dash.

### `permissions.py`

Declara la matriz central por rol técnico y perfil funcional. `ADMIN` funciona como
comodín y hereda automáticamente cualquier permiso nuevo. Las herramientas de consulta,
informes, juegos y recursos docentes son públicas. Importación, administración de
usuarios, datos de cuenta y creación persistente de juegos propios siguen protegidas.

### `__init__.py`

Marcador de paquete sin código.
