# Car Inspection API

Microservicio B2B (FastAPI) para aseguradoras y rent-a-car. Recibe fotos de vehículos,
las procesa **en memoria** (nunca toca disco local) y un modelo de clasificación binaria
(Keras `.h5`) determina si el vehículo tiene **daño** o está **intacto**. Cada inspección
se persiste en PostgreSQL y la foto se archiva en almacenamiento S3-compatible (MinIO),
recuperable después mediante una URL temporal firmada.

## Características

- `POST /inspect` — clasifica una foto (damaged/intact) y devuelve la confianza.
- `GET /history/{plate_number}` — historial de inspecciones de una matrícula.
- `GET /inspections/{id}/image` — URL temporal firmada para recuperar la foto desde MinIO.
- Autenticación por API key estática (`X-API-Key`).
- Imágenes procesadas **solo en RAM** (`io.BytesIO`); el modelo se carga **una vez** en el
  `lifespan` de FastAPI (no por request).

## Stack

FastAPI · SQLAlchemy 2.0 + Alembic · PostgreSQL 16 · Pillow + NumPy ·
TensorFlow-CPU / Keras (MobileNetV2) · boto3 + MinIO · prometheus-client · Docker Compose · uv

## Arquitectura

```
app/
├── main.py                # FastAPI + lifespan (carga modelo y clientes S3 a app.state)
├── api/
│   ├── deps.py            # get_db, rate_limit
│   └── routers/
│       ├── inspect.py     # POST /inspect
│       ├── history.py     # GET /history/{plate_number} (paginado)
│       └── images.py      # GET /inspections/{id}/image
├── core/
│   ├── config.py          # Settings (pydantic-settings, lee .env)
│   ├── security.py        # require_api_key (X-API-Key)
│   ├── ratelimit.py       # RateLimiter (ventana fija en memoria)
│   ├── errors.py          # handlers de error con formato uniforme
│   ├── logging.py         # JsonFormatter + request_id (ContextVar)
│   ├── middleware.py      # request-id, latencia y métricas por request
│   └── metrics.py         # contadores/histogramas Prometheus
├── db/
│   ├── base.py            # DeclarativeBase
│   ├── session.py         # engine + SessionLocal
│   └── models/inspection.py
├── schemas/inspection.py  # InspectionResult, InspectionRead, ImageURL, InspectionPage
├── ml/
│   ├── preprocessing.py   # bytes -> tensor (1,224,224,3) en [0,1]
│   └── classifier.py      # load_classifier + predict
└── storage/s3.py          # cliente boto3, upload, presigned URL
```

**Reglas de diseño:**

- **Imágenes solo en RAM.** El endpoint lee los bytes (`await file.read()`), los usa para
  inferencia y los sube a MinIO sin escribir nunca a disco local.
- **Modelo cargado una vez.** Se carga en el `lifespan` → `app.state.model`. Si no existe el
  `.h5`, `app.state.model = None` y `/inspect` responde `503`.
- **Inferencia bloqueante** (`predict`) y subida a S3 envueltas en `run_in_threadpool` para
  no bloquear el event loop.
- **Tipado estricto** en todo el código.

## Puesta en marcha

```bash
# 1. Copiar plantilla de entorno (incluye credenciales de dev listas para usar).
cp .env.example .env

# 2. Construir y levantar todo (db + minio + api + pgadmin).
docker compose up -d --build

# 3. Aplicar migraciones (crea la tabla "inspections").
docker compose exec api uv run alembic upgrade head
```

- API: http://localhost:8000 · Health: http://localhost:8000/health · Docs (Swagger): http://localhost:8000/docs
- MinIO consola: http://localhost:9001 · pgAdmin: http://localhost:5050

> Sin un modelo entrenado en `models/`, `/inspect` responde `503`. Ver
> [Modelo ML](#modelo-ml) para generar un placeholder o
> [Entrenamiento](#entrenamiento-transfer-learning-mobilenetv2) para uno real.

## Servicios

| Servicio  | Puerto(s)    | Para qué |
|-----------|--------------|----------|
| `api`     | 8000         | FastAPI |
| `db`      | 5432         | PostgreSQL 16 |
| `minio`   | 9000 / 9001  | S3 API / consola web |
| `pgadmin` | 5050         | Inspección visual de la DB (host=`db`, port=`5432`) |
| `prometheus` | 9090      | Scrapea `/metrics` y guarda series temporales |
| `grafana` | 3000         | Dashboards (login `GRAFANA_USER`/`GRAFANA_PASSWORD`, def. `admin`/`admin`) |

## Variables de entorno

| Variable | Por defecto | Descripción |
|----------|-------------|-------------|
| `DATABASE_URL` | — | `postgresql+psycopg://…` (en compose la api usa host `db`) |
| `API_KEY` | — | Clave estática para el header `X-API-Key` |
| `RATE_LIMIT_PER_MINUTE` | `120` | Peticiones permitidas por API key y minuto |
| `MODEL_PATH` | `models/damage_classifier.h5` | Ruta al `.h5` que carga el `lifespan` |
| `S3_ENDPOINT_URL` | — | Endpoint que la api usa para **subir** (en compose `http://minio:9000`) |
| `S3_PUBLIC_ENDPOINT_URL` | = `S3_ENDPOINT_URL` | Endpoint con el que se **firman** las presigned URLs (`http://localhost:9000`) |
| `S3_ACCESS_KEY` / `S3_SECRET_KEY` | — | Credenciales MinIO/S3 |
| `S3_BUCKET` | `car-images` | Bucket (se crea solo en el `lifespan` si no existe) |
| `S3_REGION` | `us-east-1` | Región (irrelevante en MinIO, requerida por la firma s3v4) |
| `S3_PRESIGNED_EXPIRY` | `3600` | Validez en segundos de la presigned URL |

## API

Todos los endpoints (salvo `/health`) requieren el header `X-API-Key` y están sujetos a
[rate limiting](#rate-limiting). Los errores siguen un [formato uniforme](#formato-de-errores).

| Método | Ruta | Descripción | Respuestas |
|--------|------|-------------|------------|
| `GET`  | `/health` | Liveness (sin auth) | `200 {"status":"ok"}` |
| `GET`  | `/metrics` | Métricas Prometheus (sin auth) | `200` texto plano |
| `POST` | `/inspect` | Clasifica una foto y persiste la inspección | `201` · `400` no-imagen · `422` imagen inválida · `503` sin modelo |
| `GET`  | `/history/{plate_number}` | Inspecciones de una matrícula, paginadas (desc por fecha) | `200 InspectionPage` |
| `GET`  | `/inspections/{id}/image` | Presigned URL de la foto | `200 ImageURL` · `404` no existe / sin imagen |

### `POST /inspect`

Multipart: `plate_number` (form) + `file` (imagen).

```bash
curl -H "X-API-Key: dev-secret-api-key-change-me" \
  -F "plate_number=ABC123" -F "file=@foto.jpg;type=image/jpeg" \
  http://localhost:8000/inspect
# -> {"plate_number":"ABC123","is_damaged":true,"confidence":0.9437,"image_key":"ABC123/1.jpg"}
```

Flujo: lee bytes → preprocesa a tensor `(1,224,224,3)` en `[0,1]` → `predict` →
`INSERT` en `inspections` → sube la imagen a MinIO con key `{plate}/{id}.ext` →
guarda `image_key` en el registro.

### `GET /inspections/{id}/image`

Devuelve una URL temporal firmada; el cliente descarga la imagen **directo de MinIO**, sin
pasar bytes por la API ni exponer credenciales. La URL **no** requiere API key (la firma
autoriza).

```bash
curl -H "X-API-Key: dev-secret-api-key-change-me" http://localhost:8000/inspections/1/image
# -> {"url":"http://localhost:9000/car-images/ABC123/1.jpg?X-Amz-Signature=...","expires_in":3600}
```

### `GET /history/{plate_number}`

Paginado con `limit` (1-100, def. 20) y `offset` (≥0). Devuelve un envelope con el total.

```bash
curl -H "X-API-Key: dev-secret-api-key-change-me" \
  "http://localhost:8000/history/ABC123?limit=20&offset=0"
# -> {"items":[InspectionRead, ...], "total":42, "limit":20, "offset":0}
```

## Rate limiting

Límite por API key y ventana de 1 minuto (`RATE_LIMIT_PER_MINUTE`, 120 por defecto). Cada
respuesta incluye `X-RateLimit-Limit` y `X-RateLimit-Remaining`; al superar el límite la API
responde `429` con cabecera `Retry-After`.

> El contador vive **en memoria del proceso**: con un solo worker (dev local) funciona como
> límite global. Con varios workers o instancias sería por-proceso; para un límite real
> compartido se usaría un store externo (p. ej. Redis).

## Formato de errores

Todos los errores siguen la misma forma:

```json
{ "error": { "status": 404, "message": "Inspeccion no encontrada.", "path": "/inspections/9999/image" } }
```

Los errores de validación (`422`) añaden `details` con los campos que fallaron.

## Observabilidad

Tres señales, todo local y sin dependencias pesadas (stdlib `logging` + `prometheus-client`).

### Logs estructurados (JSON)

Todos los logs de la app salen como JSON (un `logging.Formatter` custom enganchado al root
logger), filtrables por campo con `jq`, Loki, etc.:

```json
{"ts":"2026-05-24T10:48:47Z","level":"info","logger":"app","message":"modelo cargado","model_path":"models/damage_classifier.h5"}
```

Para adjuntar campos extra: `logger.info("msg", extra={"extra_fields": {...}})`.

> Las líneas `INFO: Uvicorn running...` quedan en texto plano porque uvicorn usa sus propios
> handlers (no propagan al root). Las líneas `I0000... cpu_feature_guard` las escribe el C++
> de TensorFlow directo a stderr, por debajo de Python. Ninguna es capturable por el formatter.

### Request-id y latencia

Un middleware (`app/core/middleware.py`) asigna a cada petición un `request_id` (reutiliza el
header `X-Request-ID` entrante o genera un UUID), lo devuelve en la respuesta y emite una línea
por request con método, ruta, status y `latency_ms`:

```json
{"ts":"...","level":"info","logger":"app.request","request_id":"mi-trace-123","message":"request","method":"POST","path":"/inspect","status":201,"latency_ms":142.0}
```

El `request_id` se propaga vía `ContextVar`, así que **cualquier** log emitido durante esa
petición lo incluye automáticamente (sin pasarlo a mano). El `ContextVar` es seguro entre
peticiones concurrentes (cada tarea async tiene su copia).

### Métricas (`/metrics`, modelo pull de Prometheus)

`GET /metrics` expone en formato Prometheus:

| Métrica | Tipo | Labels |
|---------|------|--------|
| `http_requests_total` | Counter | `method`, `path`, `status` |
| `http_request_duration_seconds` | Histogram | `method`, `path` |
| `inference_duration_seconds` | Histogram | — (tiempo del modelo, aislado) |
| `predictions_total` | Counter | `outcome` (`damaged`/`intact`) |

> **Cardinalidad:** la label `path` es la *plantilla* de ruta (`/history/{plate_number}`), no la
> ruta real (`/history/ABC123`). Usar la ruta real crearía una serie por cada matrícula →
> explosión de cardinalidad que tumba a Prometheus.

```bash
curl http://localhost:8000/metrics
```

### Visualización (Prometheus + Grafana)

El stack viene incluido en compose y auto-provisionado:

```
api:8000/metrics ──scrape 15s──> Prometheus:9090 ──PromQL──> Grafana:3000
```

- **Prometheus** (http://localhost:9090) — config en `monitoring/prometheus.yml`; scrapea el
  job `car-inspection-api` (`api:8000`). Estado de targets en *Status → Targets*. Permite
  lanzar PromQL a mano, p. ej. `rate(http_requests_total[1m])`.
- **Grafana** (http://localhost:3000, `admin`/`admin`) — datasource Prometheus y un dashboard
  se cargan solos desde `monitoring/grafana/provisioning/`.

Configuración (todo versionado en `monitoring/`, nada se toca a mano en la UI → reproducible):

```
monitoring/
├── prometheus.yml                              # qué scrapear (job api:8000)
└── grafana/
    ├── provisioning/
    │   ├── datasources/datasource.yml          # datasource Prometheus (uid=prometheus)
    │   └── dashboards/dashboards.yml           # provider que carga los dashboards
    └── dashboards/
        └── car-inspection.json                 # dashboard (4 paneles)
```

Para verlo:

```bash
docker compose up -d prometheus grafana
# 1. Genera tráfico: varios POST /inspect y algún GET /history.
# 2. Abre http://localhost:3000  (admin / admin).
# 3. Menú lateral -> Dashboards -> "Car Inspection API".
```

El dashboard (refresco 10s) trae 4 paneles:

| Panel | PromQL |
|-------|--------|
| Peticiones/segundo por ruta | `sum by (path) (rate(http_requests_total[1m]))` |
| Latencia HTTP p95 | `histogram_quantile(0.95, sum by (le, path) (rate(http_request_duration_seconds_bucket[5m])))` |
| Latencia de inferencia p95 | `histogram_quantile(0.95, sum by (le) (rate(inference_duration_seconds_bucket[5m])))` |
| Predicciones damaged vs intact | `sum by (outcome) (predictions_total)` |

## Almacenamiento de imágenes (MinIO / S3)

Tras la inferencia, los bytes (aún en RAM) se suben a MinIO con key `{plate_number}/{id}.ext`.
La columna `image_key` enlaza el registro con el objeto. boto3 apunta a `S3_ENDPOINT_URL`;
para AWS S3 real solo cambian endpoint y credenciales.

**Gotcha de Docker con presigned URLs:** la firma AWS incluye el `Host`. Si se firma con el
host interno de la red Docker (`minio:9000`), el navegador del host no resuelve ese nombre y
la descarga falla. Por eso se firma con `S3_PUBLIC_ENDPOINT_URL` (`localhost:9000`, lo que ve
el cliente) y no con `S3_ENDPOINT_URL` (`minio:9000`, host interno que la api usa para subir).
Un segundo cliente boto3 (`app.state.s3_public`) se encarga de firmar.

## Modelo ML

El `lifespan` carga `MODEL_PATH` en `app.state.model`. El modelo espera entrada
`(1,224,224,3)` normalizada a `[0,1]` y salida sigmoid (`P(dañado)`, umbral 0.5).

Para validar el pipeline sin entrenar, genera un placeholder (misma firma, sin entrenar):

```bash
docker compose run --rm --no-deps api uv run python scripts/make_dummy_model.py
docker compose up -d api
```

Para producción, sustituye ese `.h5` por un modelo real con la misma firma. **Reinicia la api
(`docker compose up -d api`) tras reemplazar el `.h5`** para que el `lifespan` lo recargue.

## Entrenamiento (transfer learning MobileNetV2)

`scripts/train.py` entrena por transfer learning. Dataset esperado:

```
data/train/{damaged,intact}/*.jpg
data/val/{damaged,intact}/*.jpg
```

Convención: `sigmoid = P(dañado)` (damaged=1 vía `class_names`). El modelo recibe entrada
`[0,1]` (igual que el backend) y reescala a `[-1,1]` internamente para MobileNetV2, así
`app/ml/preprocessing.py` no cambia. Exporta a `models/damage_classifier.h5`.

Incluye las cuatro mejoras del clasificador:

1. **Fine-tuning** — segunda fase que descongela las últimas capas del backbone con LR `1e-5`.
2. **Métricas serias** — precision/recall/F1 + matriz de confusión (positivo = dañado; en B2B
   un falso negativo de daño es caro, por eso se reporta el conteo de FN).
3. **Data augmentation** — flip horizontal, rotación, brillo.
4. **EarlyStopping + ModelCheckpoint** — guarda la mejor época, no la última.

Configurable por env: `EPOCHS_HEAD` (15), `EPOCHS_FINETUNE` (0), `FINE_TUNE_AT` (100).

```bash
# 1. (Opcional) dataset sintético para validar el pipeline (NO sirve como modelo real)
docker compose run --rm --no-deps api uv run python scripts/make_sample_dataset.py

# 2. Entrenar (descarga pesos ImageNet la 1ª vez)
docker compose run --rm --no-deps api uv run python scripts/train.py

# 3. Recargar el modelo en la api
docker compose up -d api
```

**Dataset real:** [anujms/car-damage-detection](https://www.kaggle.com/datasets/anujms/car-damage-detection)
(1840 train / 460 val, damaged vs whole). Descargar a `data/raw/` y reorganizar:

```bash
kaggle datasets download -d anujms/car-damage-detection -p data/raw --unzip
docker compose run --rm --no-deps api uv run python scripts/prepare_dataset.py
```

`prepare_dataset.py` mapea `data/raw/{training,validation}/{00-damage,01-whole}` a
`data/{train,val}/{damaged,intact}` (limpia los destinos antes de copiar).

### Resultado y por qué el fine-tuning está desactivado por defecto

Con backbone congelado (15 épocas) el mejor modelo alcanza **val_accuracy ~0.935,
precision ~0.94, recall ~0.93**. El fine-tuning degrada el recall a **~0.70** en este dataset
(1840 imgs): al descongelar, las estadísticas de BatchNorm heredadas de ImageNet se
desincronizan y desestabilizan el entrenamiento sobre un dataset pequeño.

Por eso `EPOCHS_FINETUNE=0` por defecto (activable por env). Además, el `ModelCheckpoint` de
la fase 2 usa `initial_value_threshold` con el mejor `val_loss` de la fase 1, de modo que
**nunca** sobreescribe el modelo con uno peor; `report()` carga el mejor desde disco.

## Migraciones

```bash
# Aplicar
docker compose exec api uv run alembic upgrade head

# Crear una nueva (autogenerada a partir de los modelos)
docker compose exec api uv run alembic revision --autogenerate -m "mensaje"
```

## Tests

Aislados: SQLite in-memory por test, `predict` mockeado, clientes S3 con `MagicMock`. No
requieren modelo ni MinIO reales. Las dev-deps no van en la imagen de producción
(`uv sync --no-dev`).

```bash
docker compose exec api uv run --group dev pytest -q
```

> El directorio `tests/` **no** está montado como volumen en compose (solo `./app`). Para
> correr tests nuevos dentro del contenedor, reconstruye la imagen (`docker compose up -d
> --build api`) o monta `./tests`.

## Modo desarrollo

El contenedor `api` monta `./app`, `./models` y `./data`, y corre `uvicorn --reload`, así que
los cambios en el código se recargan en caliente. Los cambios en variables de entorno o en
`docker-compose.yml` requieren recrear el contenedor (`docker compose up -d api`).
