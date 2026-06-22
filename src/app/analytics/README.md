# Analítica y visualizaciones

Este paquete conecta la capa de persistencia con las figuras mostradas en Dash.

## Archivos Python

### `__init__.py`

Expone la API pública: `FraIndicator`, consultas FRA/ILGA e invalidación de caché.

### `repository.py`

- `FraIndicator`: representación inmutable del catálogo relacional; `label` compone el texto mostrado en el selector.
- `get_fra_indicators()`: consulta `public.indicators` y `public.categories` en PostgreSQL.
- `get_fra_indicator_answers(code)`: busca en MongoDB un documento de `Indicator_fra`.
- `get_latest_ilga_document()`: recupera el documento `Indicator_ilga` con el año más reciente.
- `invalidate_analytics_cache()`: limpia toda la caché configurada.

Las tres lecturas están memoizadas. Ante errores de base de datos registran el fallo y devuelven una colección vacía o `None`, permitiendo que la interfaz siga cargando.

### `geography.py`

Contiene centroides aproximados de países europeos y `build_ilga_geodataframe()`. Esta función convierte los países ILGA válidos en un `GeoDataFrame` WGS84 (`EPSG:4326`) con puntos, latitud, longitud y ranking. Omite países sin coordenadas o ranking numérico.

### `figures.py`

- `build_ilga_choropleth()`: mapa coroplético europeo Plotly.
- `build_ilga_ranking_bar()`: ranking horizontal de los mejores países.
- `build_fra_country_bar()`: media de porcentajes FRA por país y número de observaciones.
- `build_matplotlib_ranking_image()`: gráfico PNG embebido como URI base64.
- `build_cached_matplotlib_ranking_image()`: versión cacheada por año.
- `build_ilga_mapbox_figure()`: puntos sobre OpenStreetMap.
- `_countries()` y `_aggregate_fra_answers()`: normalización interna de datos.

## Dependencias

PostgreSQL, MongoDB, Flask-Caching, Plotly, Matplotlib, GeoPandas y Shapely.
