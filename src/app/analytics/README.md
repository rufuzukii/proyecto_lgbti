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

## Estadisticas europeas FRA / ILGA-Europe

La pagina `/statistics` usa una capa modular nueva:

- `statistics_models.py`: modelos de consulta y validacion de un unico filtro FRA del grupo A y un unico filtro del grupo B.
- `statistics_normalizers.py`: normalizacion de codigos ISO, tipos de filtro y erratas conocidas sin perder el valor bruto usado por los datos.
- `statistics_service.py`: conversion de documentos Mongo a `DataFrame`, filtrado, agregacion y estados sin datos.
- `statistics_charts.py`: generacion centralizada de graficos Plotly para mapa, ranking, distribucion, comparador, heatmap ILGA y scatter FRA/ILGA.
- `statistics_geodata.py`: union reusable GeoPandas por codigo ISO y deteccion de paises sin geometria o duplicados.

El mapa mantiene Plotly `Choropleth` en vez de introducir Dash Leaflet porque la aplicacion ya usaba Plotly para estos mapas, no necesita token privado de Mapbox, se integra con `clickData` y reduce el cambio de dependencias y callbacks. La union GeoPandas queda preparada para incorporar geometria real europea cuando el proyecto incluya un GeoJSON o `GeoDataFrame` fuente.

Los documentos FRA se esperan en `Indicator_fra` con `answers[]` que contengan `country`, `country_code`, `answer`, `percentage` y `filters[]` como pares `{type, value}`. Los documentos ILGA se esperan en `Indicator_ilga` con `countries[]`, `ranking` y `criteria[]`. Los criterios ILGA disponibles se extraen de los metadatos importados (`category`, `indicator`, `weight`); no se inventan descripciones juridicas si el dataset no las trae.
