# Páginas administrativas

Solo deben mostrarse a usuarios autenticados con rol `admin`. Las comprobaciones y operaciones POST están en `app/dash_app.py`.

## `users.py`

- `build_admin_users_layout()`: pantalla de gestión.
- `build_access_denied_layout()`: respuesta visual sin permisos.
- `_build_users_table()` y `_build_user_row()`: formularios por usuario.
- `_role_value()`: normaliza roles históricos.
- `_message()`: mensajes accesibles.

Permite editar nombre, email, organización y rol, además de eliminar cuentas. El backend evita que un administrador se elimine a sí mismo desde esta pantalla.

## `imports.py`

- `build_admin_imports_layout()`: lista pendientes y mensajes.
- `_build_grouped_imports()` y `_build_user_group()`: agrupan por usuario.
- `_build_file_link()`: abre la revisión.
- `_build_import_modals()` y `_build_import_modal()`: muestran JSON y acciones.
- `_modal_id()`: identificador estable del modal CSS.
- `_message()`: estado/error.

Los modales funcionan con el selector CSS `:target`. Aprobar inserta según `dataset`; rechazar elimina el log pendiente.

## `__init__.py`

Marcador de paquete.
