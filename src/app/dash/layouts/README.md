# Layouts reutilizables

## `home.py`

`build_home_layout()` consulta el último documento ILGA y el catálogo FRA. Construye:

- barra de navegación;
- mapa coroplético Plotly;
- métricas de año, países e indicadores;
- acceso al panel estadístico.

`_metric()` genera cada tarjeta métrica.

## `navigation.py`

`build_navbar()` crea los enlaces globales. `_account_link()` cambia entre inicio de sesión y perfil. `_admin_link()` solo aparece para rol `admin`. `_nav_link_class()` aplica estado activo y estilos CTA.

La ruta principal de estadísticas es `/statistics`; `/stadistics` queda solo como alias de compatibilidad.

## `user_page.py`

Presenta el perfil autenticado en modo lectura o edición:

- mensajes de estado/error;
- resumen de nombre, email, organización y rol;
- formulario de actualización con CSRF;
- cambio opcional de contraseña;
- cierre de sesión.

Los helpers construyen formularios, filas de detalle, etiquetas de rol y mensajes.

## `__init__.py`

Marcador de paquete sin lógica.
