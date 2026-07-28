# Pruebas de configuración

`test_config.py` verifica:

- valores PostgreSQL por defecto;
- clave de desarrollo y `debug=True` en modo local;
- obligación de `SECRET_KEY` en producción.

No cubre aún MongoDB, hosts/puertos personalizados, booleanos inválidos ni construcción de DSN.

El propio test calcula `ROOT` con `parents[2]`, que apunta a `tests` en vez de a la raíz del repositorio. Por ello requiere ejecutar pytest con `PYTHONPATH=src` o corregir esa ruta.
