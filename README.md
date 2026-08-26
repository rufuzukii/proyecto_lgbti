# RainbowLens DataHub

RainbowLens DataHub es una aplicación web que centraliza, visualiza y analiza información social, legal y educativa sobre la realidad LGBTIQ+ en Europa y España.

Aplicación pública: [proyecto-lgbti.onrender.com](https://proyecto-lgbti.onrender.com)

## Qué es RainbowLens DataHub

El proyecto reúne datos públicos de distintas fuentes en una interfaz bilingüe ES/EN. Permite explorar diferencias entre países, consultar evolución temporal y reutilizar los resultados en actividades educativas e informes orientados a recursos humanos.

## Objetivos principales

- Facilitar la consulta de datos sociales y legales relacionados con la realidad LGBTIQ+.
- Mantener diferenciados los datos oficiales, el procesamiento realizado por RainbowLens y las proyecciones exploratorias.
- Ofrecer visualizaciones, tablas e informes comprensibles y exportables.
- Proporcionar recursos didácticos con definiciones breves y fuentes institucionales.

## Funcionalidades

- Mapa europeo y ranking legal basado en ILGA-Europe.
- Estadísticas de encuestas FRA y análisis combinado FRA + ILGA-Europe.
- Tendencias históricas y proyecciones estadísticas identificadas como estimaciones de RainbowLens.
- Consulta de información española procedente de informes de FELGTBI+.
- Diccionario, presentaciones, juegos y Espacio Docente.
- Generación de informes para contextos de diversidad, inclusión y recursos humanos.
- Registro con acceso inmediato, autenticación por roles y validación administrativa informativa.
- Contacto directo mediante [rainbowlensdatahub@gmail.com](mailto:rainbowlensdatahub@gmail.com).

## Fuentes de datos

- European Union Agency for Fundamental Rights (FRA).
- ILGA-Europe, Rainbow Map y Annual Review.
- Federación Estatal LGTBI+ (FELGTBI+).

RainbowLens procesa y visualiza estos materiales sin presentarse como afiliado ni respaldado por las instituciones de origen. Cada área conserva sus atribuciones y enlaces oficiales.

## Arquitectura general

La interfaz Dash se ejecuta sobre Flask. La API independiente utiliza FastAPI. PostgreSQL almacena cuentas y datos relacionales, MongoDB conserva datos analíticos y Supabase Storage aloja recursos compatibles con S3. La capa `analytics` separa repositorios, normalización, servicios y construcción de figuras.

## Tecnologías principales

- Python 3.14
- Dash, Flask y Flask-Login
- Plotly, Pandas y GeoPandas
- FastAPI
- PostgreSQL y psycopg
- MongoDB y PyMongo
- Supabase Storage y boto3
- Gunicorn y Render

## Estructura básica del proyecto

```text
src/app/
├── analytics/       Datos, servicios y visualizaciones
├── api/             API FastAPI
├── auth/            Registro, login y autorización
├── dash/            Interfaz, páginas y recursos estáticos
├── edu/             Catálogo y servicios didácticos
├── import_to_db/    Importadores y validación de fuentes
├── reports/         Construcción y exportación de informes
└── users/           Modelo y gestión de usuarios
tests/               Pruebas unitarias, integración, E2E lógico y humo
scripts/             Utilidades de mantenimiento verificables
render.yaml          Definición del servicio de producción
wsgi.py              Entrada WSGI para Gunicorn
```

## Instalación local

Requiere Python 3.14.

```bash
python -m venv .venv
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Configuración

La configuración local puede cargarse desde un archivo `.env` no versionado. En Render, los mismos nombres se configuran desde el panel de variables de entorno.

Variables principales:

```text
APP_ENV
LOCAL_MODE
SECRET_KEY
DATABASE_URL
POSTGRES_SSL_MODE
MONGO_URI
MONGO_DB
```

Variables opcionales según los servicios utilizados:

```text
API_KEY
API_KEYS
SUPABASE_URL
SUPABASE_S3_ENDPOINT
SUPABASE_S3_ACCESS_KEY
SUPABASE_S3_SECRET_KEY
SUPABASE_S3_REGION
SUPABASE_STORAGE_BUCKET
DIDACTIC_SLIDES_BUCKET
PRIVACY_CONTROLLER_NAME
PRIVACY_CONTACT_EMAIL
```

La aplicación no utiliza SMTP ni requiere variables de correo transaccional.

## Ejecución

```bash
rainbowlens-dash
```

La API puede iniciarse de forma independiente con:

```bash
uvicorn app.api:app
```

## Tests

```bash
python -m compileall .
python -m pytest
python -m pytest --cov=app --cov-report=term-missing
python -m pyright
ruff check .
```

Para las pruebas de humo contra un despliegue real se define `RENDER_EXTERNAL_URL` y se ejecuta `python -m pytest tests/smoke`.

## Despliegue

`render.yaml` describe un único servicio web Gunicorn y utiliza `GET /health` como comprobación de vida. Los secretos de PostgreSQL, MongoDB y almacenamiento se proporcionan únicamente mediante variables seguras de Render.

## Privacidad y uso de datos

La aplicación trabaja principalmente con fuentes públicas agregadas. Las cuentas conservan los datos necesarios para autenticación, perfil y funciones docentes. No se envían correos automáticos ni se comprueba el control de la dirección registrada. La política de privacidad de la aplicación detalla responsables, conservación, derechos y proveedores.

## Fuentes y atribuciones

Las denominaciones, publicaciones y datasets oficiales mantienen su nombre original. Las transformaciones, normalizaciones, comparaciones y proyecciones propias se identifican como procesamiento de RainbowLens DataHub.

## Estado del proyecto

Proyecto académico en desarrollo activo como Trabajo de Fin de Grado. La arquitectura actual es común a local y Render. La integración futura de un servicio transaccional compatible con producción queda fuera del alcance de esta versión.
