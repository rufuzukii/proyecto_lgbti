# Exportación de gráficos

- `__init__.py`: marcador de paquete.
- `exporter.py`: define `export_chart(format_name)`, que solo devuelve el formato solicitado y estado `pending`.

La exportación real a PNG, SVG, PDF o HTML no está implementada. Las visualizaciones operativas se construyen en `app/analytics/figures.py`.
