# Páginas de sesión

## `login.py`

`build_login_layout()` genera un formulario HTML POST hacia `/auth/login`, con token CSRF y ruta `next`. `_message()` presenta errores de credenciales, límite de intentos, sesión o almacenamiento.

## `register.py`

`build_register_layout()` solicita nombre, email, organización y contraseña. Envía a `/auth/register`; las cuentas se crean con rol `common`. `_message()` presenta errores.

## `__init__.py`

Marcador de paquete.

La validación y escritura no se ejecutan en estos archivos, sino en las rutas Flask registradas por `dash_app.py`.
