# Páginas Dash

## Archivos Python

- `statistics.py`: panel analítico operativo; combina Plotly, Dash-Leaflet, Mapbox, Matplotlib y GeoPandas. Registra un callback que actualiza el gráfico FRA al cambiar el indicador.
- `upload.py`: carga de hasta tres CSV de 5 MB, selección de fuente, parseo, sincronización FRA en PostgreSQL y alta en la cola de revisión.
- `about.py`: vacío; no implementa página.
- `didactics.py`: vacío; no implementa página.
- `report.py`: vacío; no implementa página.
- `__init__.py`: marcador de paquete.

## `statistics.py`

`build_statistics_layout()` carga el catálogo FRA, el último ILGA, el primer indicador y el GeoDataFrame. Los helpers crean paneles, marcadores Leaflet, resumen espacial y texto descriptivo. `register_statistics_callbacks()` actualiza figura y resumen FRA.

## `upload.py`

Funciones principales:

- `_decode_upload_contents()`: decodifica base64 y calcula tamaño.
- `build_upload_layout()`: formulario visual.
- `register_upload_callbacks()`: valida y procesa la subida.
- `normalize_upload_values()`: unifica valores simples/múltiples.
- `parse_csv_by_source()`: delega a FRA o ILGA; FELGTB lanza `NotImplementedError`.
- `count_payload_documents()`: contabiliza documentos.
- `build_error_message()` y `build_success_message()`: respuestas UI.

La subida no exige autenticación. Si existe sesión, asocia el `user_id`; en caso contrario registra una importación anónima.
