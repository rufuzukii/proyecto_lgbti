# RainbowLens DataHub

RainbowLens DataHub es una aplicación web que centraliza, visualiza y analiza información social, legal y educativa sobre la realidad LGBTIQ+ en Europa y España.

Versión actual del código: **1.0.0**.

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
- Generación de informes para contextos de diversidad, inclusión y recursos humanos, con narrativas revisables antes de crear un PDF editable.
- Registro con inicio de sesión automático, acceso inmediato y autenticación por roles.
- Contacto directo mediante [rainbowlensdatahub@gmail.com](mailto:rainbowlensdatahub@gmail.com).

## Fuentes de datos

- European Union Agency for Fundamental Rights (FRA).
- ILGA-Europe, Rainbow Map y Annual Review.
- Federación Estatal LGTBI+ (FELGTBI+).

RainbowLens procesa y visualiza estos materiales sin presentarse como afiliado ni respaldado por las instituciones de origen. Cada área conserva sus atribuciones y enlaces oficiales.

## Arquitectura general

RainbowLens DataHub es un monolito modular: un único servicio Dash sobre Flask, organizado internamente por áreas funcionales. Los módulos comparten el mismo proceso y llaman a servicios Python; no existe comunicación HTTP interna. La API FastAPI es una interfaz opcional sobre los mismos módulos y no forma parte del servicio desplegado en Render.

PostgreSQL almacena cuentas y datos relacionales, MongoDB conserva datos analíticos y Supabase Storage aloja recursos compatibles con S3. Sus clientes se centralizan en `infrastructure/`.

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
├── api/             Interfaz FastAPI opcional
├── core/            Configuración, seguridad, permisos y logging
├── infrastructure/  MongoDB, PostgreSQL, Storage y caché
├── modules/         Áreas funcionales del monolito
│   ├── home/        Inicio y contexto legal
│   ├── statistics/  Estadísticas FRA/ILGA y visualizaciones
│   ├── trends/      Series históricas y forecasting
│   ├── spain/       Informes FELGTBI+ de España
│   ├── didactics/   Diccionario, juegos y espacio docente
│   ├── reports/     Configuración y generación de informes
│   ├── account/     Cuenta, usuarios y privacidad
│   ├── administration/
│   └── imports/     Pipelines de importación en runtime
├── shared/          Componentes y lógica de datos reutilizada
└── web/             Factory Dash, rutas, navegación y assets
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

`pyproject.toml` es la única fuente de dependencias y configuración de empaquetado, tanto en
local como en Render.

### Exportación de gráficas para informes

En local, Kaleido utiliza un Chrome o Chromium ya instalado y detectable. El diagnóstico
reutilizable comprueba las versiones, el navegador, una figura mínima, el batch de Plotly y el
helper de RainbowLens:

```bash
python scripts/check_chart_export.py
```

En Render se mantiene el runtime nativo de Python. `scripts/render_build.sh` descarga la versión
de Chrome for Testing fijada por Choreographer dentro de `$VENV_ROOT/kaleido-chrome`, valida el
binario, sus librerías y una ejecución headless, y ejecuta el diagnóstico completo. El archivo
creado queda dentro del artefacto desplegable del virtualenv. `scripts/render_start.sh` vuelve a
calcular la misma ruta, exporta `BROWSER_PATH` —la variable que Choreographer 1.3 consume— y exige
una exportación PNG real antes de iniciar Gunicorn. Un fallo en cualquiera de estos pasos cancela
el despliegue.

La prueba de integración que incluye batch e informes social, legal y legal con todos los países
es opt-in para CI o un entorno production-like:

```bash
RUN_BROWSER_INTEGRATION=1 python -m pytest tests/integration/test_chart_export_production_like.py
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
```

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
python -m compileall src scripts tests
python -m pytest
python -m pytest --cov=app --cov-report=term-missing
python -m pyright
ruff check .
ruff format --check .
python -m bandit -q -lll -r src scripts
python -m vulture src scripts tests --min-confidence 90
python -m pip_audit
```

`python -m pytest tests/smoke` ejecuta comprobaciones de humo con el cliente Flask local; no despliega ni valida el servicio remoto de Render. La comprobación de producción se realiza contra la URL pública después del despliegue.

## Despliegue

`render.yaml` describe un único servicio web Gunicorn y utiliza `GET /health` como comprobación de vida. Los secretos de PostgreSQL, MongoDB y almacenamiento se proporcionan únicamente mediante variables seguras de Render.

## Privacidad y uso de datos

La aplicación trabaja principalmente con fuentes públicas agregadas. Las cuentas conservan los datos necesarios para autenticación, perfil y funciones docentes. No se envían correos automáticos ni se comprueba el control de la dirección registrada. La política de privacidad de la aplicación detalla responsables, conservación, derechos y proveedores.

## Fuentes y atribuciones

Las denominaciones, publicaciones y datasets oficiales mantienen su nombre original. Las transformaciones, normalizaciones, comparaciones y proyecciones propias se identifican como procesamiento de RainbowLens DataHub.
