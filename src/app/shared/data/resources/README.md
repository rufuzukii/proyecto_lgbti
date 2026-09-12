# Recursos geográficos

Recursos geográficos versionados y reutilizados por los servicios de datos. El GeoJSON europeo se
regenera con la utilidad `app.shared.data.build_europe_geojson`:

```bash
python -m app.shared.data.build_europe_geojson
```

La utilidad descarga los límites de Natural Earth, selecciona los países del catálogo de la
aplicación y recorta y simplifica sus geometrías. Por defecto, guarda el resultado en
`europe_countries.geojson`, junto a este README, independientemente del directorio de ejecución.
Se ejecuta manualmente cuando hay que regenerar el recurso.

Para utilizar un ZIP local o guardar el resultado en otra ubicación:

```bash
python -m app.shared.data.build_europe_geojson --source countries.zip --output europe.geojson
```

La opción `--tolerance` permite ajustar la simplificación de los contornos (por defecto, `0.02`).
