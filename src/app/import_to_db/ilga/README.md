# Importador ILGA Rainbow Map

## `importer.py`

- `parse_ilga_csv()` lee un archivo UTF-8 con BOM opcional.
- `parse_ilga_csv_text()` valida estructura, resuelve año y crea el documento.
- `extract_ilga_year()` busca un año `20xx` en el nombre.
- `generate_ilga_json()` procesa varios archivos y conserva un documento por año.
- `_parse_criteria()` interpreta categoría, indicador y peso desde las tres primeras filas.
- `_parse_countries()` extrae código, país, ranking y valores de criterios.

Salida:

```json
{
  "id": "ObjectId serializado",
  "dataset": "ilga_rainbow_map",
  "year": 2026,
  "countries": []
}
```

## `mongo.py`

Valida dataset, año y países, convierte el identificador y hace upsert en `Indicator_ilga` por `(dataset, year)`.

Usa únicamente `$setOnInsert`: si el año ya existe no actualiza sus datos, tratándolos como publicación estática.

## `__init__.py`

Expone constantes, parsers e inserción MongoDB.
