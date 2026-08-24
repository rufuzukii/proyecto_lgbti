# Analítica y visualizaciones

Este paquete conecta la capa de persistencia con las figuras mostradas en Dash.

## Archivos Python

### `__init__.py`

Expone la API pública: `FraIndicator`, consultas FRA/ILGA e invalidación de caché.

### `repository.py`

- `FraIndicator`: representación inmutable del catálogo relacional; `label` compone el texto mostrado en el selector.
- `get_fra_indicators()`: consulta `public.indicators` y `public.categories` en PostgreSQL.
- `get_fra_indicator_answers(code, category, year)`: resuelve la colección desde el catálogo central de encuestas y fusiona los documentos coincidentes de esa edición.
- `get_latest_ilga_document()`: recupera el documento `Indicator_ilga` con el año más reciente.
- `invalidate_analytics_cache()`: limpia toda la caché configurada.

Las tres lecturas están memoizadas. Ante errores de base de datos registran el fallo y devuelven una colección vacía o `None`, permitiendo que la interfaz siga cargando.

### `geography.py`

Contiene códigos ISO y centroides aproximados reutilizados por las figuras Plotly. No construye
un `GeoDataFrame`: la unión GeoPandas experimental carecía de consumidores y se retiró.

### `figures.py`

- `build_ilga_choropleth()`: mapa coroplético europeo Plotly.
- `build_fra_choropleth()`: mapa FRA con selección de respuesta y filtros.
- helpers privados: normalización territorial y de respuestas para ambos mapas de Inicio.

Los constructores antiguos de rankings, barras, heatmaps y Mapbox se retiraron al no tener
consumidores. Las figuras de Estadísticas se construyen en `statistics_charts.py`.

## Dependencias

PostgreSQL, MongoDB, la caché TTL local acotada, Plotly y Pandas.

## Estadísticas europeas FRA

La página `/statistics` selecciona una edición FRA mediante `fra_surveys.py`. Las dos ediciones activas son 2023 (`Indicator_fra`) y 2019 (`Indicator_fra_2019`). El año visible se obtiene de la configuración, no del nombre de MongoDB.

El dashboard usa una capa modular:

- `statistics_models.py`: modelos de consulta y validación de un único filtro FRA del grupo A y un único filtro del grupo B.
- `statistics_normalizers.py`: normalización de códigos ISO, tipos de filtro y erratas conocidas sin perder el valor bruto usado por los datos.
- `statistics_service.py`: conversión de documentos Mongo a `DataFrame`, filtrado, agregación y estados sin datos.
- `statistics_charts.py`: generación centralizada de gráficos Plotly para mapa, ranking, distribución, comparador, heatmap legal y visualizaciones combinadas. Estadísticas muestra cuadrantes y diferencia de posiciones cuando la semántica es segura; el constructor de dispersión se reutiliza únicamente en informes combinados que lo solicitan.

El dashboard ejecuta una consulta analítica principal por selección y reutiliza el
resultado normalizado para mapa, ranking, detalle y tabla. En producción los
catálogos, marcos FRA por indicador/año y resultados agregados usan una caché local
acotada y con caducidad; las claves incluyen la generación de la fuente para que una importación
invalide solo sus datos. La geometría del mapa se conserva como GeoJSON estático y
GeoPandas se carga de forma diferida únicamente cuando hacen falta centroides.

La interfaz distingue `INITIAL`, `LOADING`, `READY`, `NO_DATA` y `ERROR`. Durante
una consulta completa el contenido anterior permanece oculto y no se construyen
figuras iniciales vacías.

El mapa mantiene Plotly `Choropleth`: no necesita token privado de Mapbox, se integra con
`clickData` y evita una dependencia geoespacial que no participaba en el flujo real.

Los documentos FRA se esperan en la colección configurada para cada encuesta, con `answers[]` que contengan `country`, `country_code`, `answer`, `percentage` y `filters[]` como pares `{type, value}`. Los documentos ILGA se esperan en `Indicator_ilga` con `countries[]`, `ranking` y `criteria[]`. Los criterios ILGA disponibles se extraen de los metadatos importados (`category`, `indicator`, `weight`); no se inventan descripciones jurídicas si el dataset no las trae.

### Radar de experiencia real y protección legal

El mapeo versionado `fra-ilga-v1` es explícito y solo incluye equivalencias presentes en ambas fuentes:

| Dimensión común | FRA | Transformación FRA | ILGA-Europe |
| --- | --- | --- | --- |
| Igualdad y no discriminación | `D1_1`, respuesta `Yes` | `100 - porcentaje` | categoría `Equality & non-discrimination` |
| Bienes y servicios | `D1_2_f`, respuesta `Yes` | `100 - porcentaje` | criterio con prefijo `Goods & services` |
| Educación | `C9_E` y `C9_C`, respuesta `Never` | media de porcentajes publicados disponibles | criterio con prefijo `Education` |
| Salud | `G16`, respuesta `Very good` | porcentaje publicado | criterio con prefijo `Health` |
| Acceso a organismos de igualdad | `C20_Any_EB`, respuesta `Yes` | porcentaje publicado | criterio con prefijo `Equality body mandate` |

Los valores FRA no se recalculan. Solo se invierten los dos indicadores negativos declarados en la tabla. Los criterios ILGA se expresan en escala 0–100 mediante `100 * suma(valor * peso) / suma(peso disponible)`. Un país necesita al menos tres dimensiones con valor en ambas fuentes; los ausentes permanecen como nulos. La comparación es descriptiva y no implica causalidad, especialmente cuando los años FRA e ILGA difieren.
