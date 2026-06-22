# Importador FRA

Procesa CSV de EU LGBTIQ Survey III y produce un documento por pregunta.

## `importer.py`

Capa tolerante de lectura:

- admite alias de cabeceras en inglés/español;
- detecta delimitador mediante pandas;
- prueba `utf-8-sig`, `utf-8`, `cp1252` y `latin-1` al leer archivos;
- extrae metadatos y notas al pie de filas finales;
- obtiene filtros tanto de columnas como de la ruta del archivo;
- resuelve códigos ISO2 y agregados `EUxx`;
- separa `specific_category > question` y también subpartes con `/`;
- genera códigos `fra_<sha1>` si falta el código externo;
- produce advertencias de validación.

Clases:

- `FraPathContext`: contexto inferido de carpetas/archivo.
- `IndicatorQuestionParts`: partes normalizadas de la pregunta.

Funciones públicas:

- `parse_answer_survey_csv()` y `parse_answer_survey_csv_text()`;
- `convert_fra_csv_files()`;
- `generate_fra_json()`.

El resto de funciones normaliza filas, filtros, metadatos, rutas, códigos, países y validación.

## `payload.py`

Convierte la salida rica del importador al JSON final:

```json
{
  "id": "ObjectId serializado",
  "code": "D1_1",
  "dataset": "eu_lgbtiq_survey_iii",
  "category": "Discrimination",
  "specific_category": "Discrimination in areas of life",
  "question": "Felt discriminated at work",
  "answers": []
}
```

Agrupa por identidad completa `(code, category, specific_category, question)`, evita respuestas duplicadas y transforma filtros a listas `{type, value}`. Devuelve un objeto si hay una sola pregunta y una lista si hay varias.

## `indicators.py`

Sincroniza PostgreSQL:

- crea o recupera `categories`;
- inserta/actualiza `indicators` por `code`;
- conserva y amplía tipos de respuesta;
- actualiza pregunta y categoría específica.

`upsert_indicators_from_json()` acepta un documento, una lista o el formato antiguo con `questions`.

## `mongo.py`

Inserta en `Indicator_fra` mediante upsert. La clave lógica es:

`code + category + specific_category + question`.

Convierte `id` a `_id: ObjectId`, elimina metadatos intermedios y añade respuestas con `$addToSet/$each`, evitando duplicados exactos.

## `__init__.py`

Expone parsers, constructor de payload, sincronización PostgreSQL e inserción MongoDB.
