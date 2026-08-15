# Importador ILGA Rainbow Map

## `importer.py`

- `parse_ilga_csv()` y `parse_ilga_csv_text()` adaptan el CSV oficial al documento anual.
- `parse_ilga_json()` y `parse_ilga_json_text()` son la entrada canónica para JSON.
- La validación exige `dataset`, año coherente con el nombre del archivo, países, códigos ISO
  admitidos, puntuaciones numéricas finitas y países no duplicados.
- La puntuación histórica de `criteria` se conserva exactamente y se adapta a `ranking`.
- Los años 2011 y 2012 reciben metadata anual de normalización; sus valores no se recalculan.

Salida canónica:

```json
{
  "id": "ObjectId serializado",
  "dataset": "ilga_rainbow_map",
  "year": 2011,
  "source_name": "ILGA-Europe Rainbow Map",
  "normalization": {
    "applied": true,
    "method": "linear_min_max",
    "original_min": -7,
    "original_max": 17,
    "target_min": 0,
    "target_max": 100
  },
  "countries": []
}
```

## `mongo.py`

Persiste documentos anuales en `Indicator_ilga` mediante una sola lectura previa y una operación
`bulk_write`. La identidad física es `(dataset, year)` y los códigos de país deben ser únicos dentro
del documento. No usa `upsert`: una edición ya existente se compara y se omite, registrando los
campos diferentes, conforme al carácter inmutable de la publicación.

## `historical.py`

Carga una carpeta completa pasando cada JSON por `parse_ilga_json()` antes de persistir. El año 2026
se detecta dentro del JSON y se omite antes de invocar cualquier escritura.

```powershell
$env:PYTHONPATH='src'
.\.venv\Scripts\python.exe -m app.import_to_db.ilga.historical `
  '<ruta-datos-ilga>' --dry-run
```

Sin `--dry-run`, crea/verifica el índice único, inserta todos los años nuevos en un lote e invalida
las cachés de analítica legal y Tendencias.
