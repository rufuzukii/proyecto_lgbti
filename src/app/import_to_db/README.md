# Importacion de CSV a bases de datos

Este paquete contiene la logica de conversion de archivos CSV externos a documentos JSON revisables antes de insertarlos definitivamente en MongoDB y PostgreSQL.

El objetivo no es insertar directamente cada CSV subido por un usuario. El flujo correcto es:

1. El usuario sube un CSV desde la aplicacion.
2. La aplicacion convierte el CSV a una estructura JSON normalizada.
3. El JSON se guarda en PostgreSQL dentro de `import_logs.file_json`.
4. El registro queda con `status = 'pending'`.
5. Un administrador revisa el JSON generado.
6. Si se aprueba, se inserta en MongoDB y se actualizan las tablas relacionales necesarias.
7. Si se rechaza o falla, se registra el motivo en `error_message`.

Este enfoque permite trazabilidad, revision manual y evita contaminar MongoDB con datos mal interpretados.

## Modulos

- `fra_importer.py`: importador para CSV de FRA / EU LGBTIQ Survey.
- `rainbow_importer.py`: importador para CSV de Rainbow Map.
- `import_log.py`: registro de importaciones pendientes o fallidas en PostgreSQL.
- `utils.py`: utilidades compartidas de normalizacion y conversion de valores.
- `__init__.py`: exporta las funciones publicas del paquete.

## Flujo de importacion

### 1. Conversion del CSV

Para FRA, el punto de entrada principal es:

```python
from app.import_to_db import generate_fra_json

results = generate_fra_json("data/imports/Discrimination")
```

`generate_fra_json()` busca CSV de forma recursiva con `rglob("*.csv")`. Esto es importante porque los datos FRA suelen estar organizados en carpetas que tambien contienen informacion semantica:

```text
Discrimination/
  Felt discriminated in the 12 months before the survey/
    Yes/
      Age/
        18-24/
          GE-Cisgender women.csv
```

La ruta anterior se interpreta como:

- `category`: `Discrimination`
- `topic`: `Discrimination`
- `question`: `Felt discriminated in the 12 months before the survey`
- `answer`: `Yes`
- `filters.age_group`: `18-24`
- `filters.gender_expression`: `Cisgender women`

Si el CSV ya contiene columnas equivalentes, los valores del CSV tienen prioridad sobre los derivados desde la ruta.

### 2. Registro como pendiente

Despues de convertir el CSV, la API registra el JSON en `import_logs`:

```python
from app.import_to_db import register_pending_import

register_pending_import(
    file_name="GE-Cisgender women.csv",
    file_json=generated_json,
    user_id=user_id,
    source_id=source_id,
)
```

El estado inicial debe ser:

```text
pending
```

Este registro funciona como cola de revision manual.

### 3. Revision por administrador

La aplicacion debe mostrar al administrador:

- nombre del archivo original;
- usuario que lo subio;
- fuente de datos;
- JSON generado;
- avisos de validacion;
- fecha de subida;
- estado actual.

El administrador deberia poder marcar el registro como:

- `approved`: datos revisados y listos para insertar;
- `rejected`: datos rechazados;
- `failed`: error tecnico durante la conversion o insercion;
- `imported`: datos ya insertados definitivamente.

Actualmente el paquete genera el JSON y lo deja preparado para esta revision. La pantalla de administracion y la insercion final en MongoDB pueden implementarse encima de `import_logs`.

## Logica especifica de FRA

`fra_importer.py` esta pensado para CSV heterogeneos de FRA. La implementacion intenta ser tolerante porque habra miles de archivos y no todos tendran exactamente las mismas columnas.

### Cabeceras flexibles

Las cabeceras se normalizan con `normalize_header()`:

```text
Gender Expression -> gender_expression
País              -> pais
Question Code     -> question_code
```

Despues se aplican alias. Por ejemplo:

- `pais`, `country_name`, `territory` -> `country`
- `pregunta`, `indicator`, `indicador` -> `question`
- `percentage`, `percent`, `porcentaje`, `value` -> `percentage`
- `question_code`, `indicator_code`, `codigo_pregunta` -> `external_code`

### Footer de FRA

Muchos CSV de FRA incluyen al final filas como:

```text
‡,small sample size
ą,not available due to small sample size
Source:,EU LGBTIQ Survey III, 2023
Date:,2026-02-27
Question Code:,D1_1
Hyperlink:,http://fra.europa.eu/...
```

Estas filas no son datos de paises. El importador las extrae como metadatos y no las inserta como respuestas.

Resultado:

- `metadata.source`
- `metadata.date`
- `metadata.external_code`
- `metadata.footnotes`
- `hyperlink` al final del documento JSON

Si una respuesta tiene `notes = "‡"`, se añade tambien:

```json
{
  "notes": "‡",
  "note_text": "small sample size"
}
```

### Documento JSON generado

La salida de FRA agrupa respuestas por indicador/pregunta:

```json
{
  "source": "EU LGBTIQ Survey III, 2023",
  "source_type": "EU_SURVEY",
  "category": "Discrimination",
  "topic": "Discrimination",
  "question": "Discrimination in areas of life > Felt discriminated...",
  "external_code": "D1_1",
  "question_path": [
    "Discrimination in areas of life",
    "Felt discriminated..."
  ],
  "metadata": {
    "schema_version": 1,
    "file_name": "GE-Cisgender women.csv",
    "requires_review": true,
    "date": "2026-02-27"
  },
  "answers": [
    {
      "country": "Austria",
      "country_code": "AT",
      "country_scope": "country",
      "answer": "Yes",
      "percentage": 36.0,
      "raw_percentage": "36",
      "notes": "",
      "note_text": "",
      "date": "2026-02-27",
      "filters": {
        "age_group": "18-24",
        "gender_expression": "Cisgender women"
      }
    }
  ],
  "validation": {
    "status": "ready",
    "warnings": []
  },
  "hyperlink": "http://fra.europa.eu/..."
}
```

### Validacion

Cada documento incluye un bloque `validation`.

Estados posibles:

- `ready`: no se han detectado avisos basicos.
- `review_required`: hay avisos que debe revisar un administrador.

Avisos actuales:

- `missing_external_code`: no hay codigo externo ni se pudo generar uno.
- `empty_answers`: el documento no contiene respuestas.
- `unknown_country_code:...`: hay paises que no se pudieron mapear a ISO2.
- `invalid_percentage:N`: hay porcentajes no vacios que no se pudieron convertir a numero.

Aunque el estado sea `ready`, el registro se guarda igualmente como `pending` en PostgreSQL. `ready` solo indica que la validacion automatica no ha visto problemas obvios.

## Relacion con PostgreSQL

La tabla `import_logs` debe guardar el JSON pendiente. El esquema minimo recomendado es:

```sql
CREATE TABLE import_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    source_id UUID REFERENCES data_sources(id),
    file_name TEXT NOT NULL,
    file_json JSONB,
    status TEXT NOT NULL,
    records_inserted INT DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

Si la tabla ya existe sin `file_json`:

```sql
ALTER TABLE import_logs ADD COLUMN IF NOT EXISTS file_json JSONB;
```

Estados recomendados:

```sql
ALTER TABLE import_logs
ADD CONSTRAINT import_logs_status_check
CHECK (status IN ('pending', 'approved', 'rejected', 'failed', 'imported'));
```

No conviene guardar el estado de revision en `users`. Un usuario puede subir muchos archivos y cada archivo necesita su propio estado. Por eso el estado pertenece a `import_logs`.

## Relacion con MongoDB

MongoDB debe recibir solo documentos aprobados.

Flujo recomendado:

1. Buscar en PostgreSQL importaciones con `status = 'approved'`.
2. Leer `file_json`.
3. Insertar los documentos en la coleccion MongoDB correspondiente.
4. Actualizar `records_inserted`.
5. Cambiar `status` a `imported`.

Para FRA, una coleccion razonable seria:

```text
fra_answer_survey
```

Cada documento representa una pregunta/indicador y contiene un array `answers` con los valores por pais y filtros.

## Relacion con tablas relacionales

PostgreSQL debe mantener los datos estructurales y de trazabilidad:

- `users`: quien sube el archivo.
- `data_sources`: fuente del dataset, por ejemplo FRA.
- `categories`: categoria general.
- `indicators`: pregunta o variable importada.
- `countries`: codigos ISO y metadatos de pais.
- `import_logs`: cola de revision y auditoria.

Para FRA, `external_code` debe usarse como referencia para `indicators.code` cuando exista `Question Code` en el CSV, por ejemplo `D1_1`.

Si no existe codigo externo, el importador genera uno estable con prefijo `fra_` a partir de fuente, categoria, tema y pregunta.

## Errores y tolerancia

El importador intenta tolerar:

- delimitadores `,`, `;`, tabulador y `|`;
- archivos `utf-8`, `utf-8-sig`, `cp1252` y `latin-1`;
- cabeceras en ingles o espanol;
- filtros en columnas o derivados desde la ruta;
- porcentajes vacios;
- agregados como `EU27`.

Pero no debe ocultar todos los problemas. Si algo no se puede interpretar, debe quedar reflejado en `validation.warnings` para revision manual.

## Pruebas

Ejecutar:

```powershell
$env:PYTHONPATH='C:\Users\rufuzuki\Desktop\Github_TFG\proyecto_lgbti\src'
.\.venv\Scripts\python.exe -m pytest -q
```

Las pruebas cubren:

- normalizacion de cabeceras con acentos;
- exclusion del footer FRA;
- extraccion de metadatos del footer;
- resolucion de notas al pie;
- recorrido recursivo de CSV;
- derivacion de filtros desde carpetas.

## Pendiente de implementar

- Endpoint o pantalla de administrador para revisar `import_logs.status = 'pending'`.
- Acciones `approve` y `reject`.
- Insercion final en MongoDB tras aprobacion.
- Upsert de `categories` e `indicators` en PostgreSQL usando los metadatos del JSON.
- Registro del numero real de documentos insertados en `records_inserted`.
- Indices MongoDB sobre `external_code`, `answers.country_code` y filtros usados con frecuencia.
