# Car Inspection API

Microservicio B2B (FastAPI) que recibe fotos de vehículos, las procesa **en memoria**
y un modelo de clasificación binaria (Keras `.h5`) determina si hay **daño** o el
vehículo está **intacto**. Resultados persistidos en PostgreSQL.

## Stack
FastAPI · SQLAlchemy 2.0 + Alembic · PostgreSQL 16 · Pillow · TensorFlow/Keras (Fase 3) · Docker · uv

## Roadmap
- **Fase 1** — Infra + DB (este estado): docker-compose, modelo `Inspection`, migraciones.
- **Fase 2** — Estructura FastAPI, `lifespan`, `POST /inspect` (mock con Pillow).
- **Fase 3** — Integración del modelo `.h5` + preprocesamiento de tensores.
- **Fase 4** — API Keys (`X-API-Key`) + `GET /history/{plate_number}`.

## Puesta en marcha (Fase 1)

```bash
# 1. Copiar plantilla de entorno (ya hay un .env de dev incluido).
cp .env.example .env

# 2. Levantar la base de datos.
docker compose up -d db

# 3. Verificar salud de Postgres.
docker compose exec db pg_isready

# 4. Aplicar migraciones (crea la tabla "inspections").
#    Opcion A (dentro del contenedor api, no requiere uv/pg local):
docker compose up -d api
docker compose exec api uv run alembic upgrade head
#    Opcion B (host local, requiere uv + Postgres accesible en localhost:5432):
uv run alembic upgrade head

# 5. pgAdmin para inspeccion visual.
docker compose up -d pgadmin
# -> http://localhost:5050  (credenciales en .env)
#    Registrar servidor: host=db, port=5432, user/db segun .env.
```

API health: http://localhost:8000/health · Docs: http://localhost:8000/docs

## Crear nuevas migraciones (autogenerado)
```bash
docker compose exec api uv run alembic revision --autogenerate -m "mensaje"
docker compose exec api uv run alembic upgrade head
```

## Modelo ML (Fase 3)
El servicio carga `MODEL_PATH` (`models/damage_classifier.h5`) en el `lifespan`. Si no
existe, `/inspect` responde `503`. Sin un modelo entrenado, genera un placeholder sin
entrenar (misma entrada `(224,224,3)`, salida sigmoid):
```bash
docker compose run --rm --no-deps api uv run python scripts/make_dummy_model.py
docker compose up -d api
```
Para producción, sustituye ese `.h5` por un modelo real con la misma firma.

Probar inferencia (requiere API key):
```bash
curl -H "X-API-Key: dev-secret-api-key-change-me" \
  -F "plate_number=ABC123" -F "file=@foto.jpg;type=image/jpeg" \
  http://localhost:8000/inspect
```

## Almacenamiento de imagenes (MinIO / S3)
Las imagenes se procesan en RAM y, tras la inferencia, se suben a MinIO (S3-compatible)
con key `{plate_number}/{id}.ext`. La columna `image_key` enlaza el registro con el objeto.
boto3 apunta a `S3_ENDPOINT_URL`; para AWS S3 real solo cambian endpoint y credenciales.

- API S3: http://localhost:9000
- Consola: http://localhost:9001 (`MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` del `.env`)
- Bucket (`S3_BUCKET`) se crea solo en el `lifespan` si no existe.

## Tests
Aislados (SQLite in-memory, `predict` mockeado, S3 con `MagicMock`); no requieren modelo
ni MinIO reales. Dev-deps no van en la imagen de produccion (`uv sync --no-dev`):
```bash
docker compose exec api uv run --group dev pytest -q
```

## Entrenamiento (transfer learning MobileNetV2)
`scripts/train.py` espera el dataset en:
```
data/train/{damaged,intact}/*.jpg
data/val/{damaged,intact}/*.jpg
```
El modelo recibe entrada `[0,1]` (igual que el backend) y reescala a `[-1,1]` internamente.
Convencion: `sigmoid = P(danado)` (damaged=1 via `class_names`). Exporta a
`models/damage_classifier.h5`; reinicia la api para recargarlo.

Entrena en 2 fases (backbone congelado → fine-tuning de las ultimas capas con LR 1e-5),
con data augmentation, EarlyStopping + ModelCheckpoint (guarda la mejor epoca) y reporte
final precision/recall/F1 + matriz de confusion. Env: `EPOCHS_HEAD`, `EPOCHS_FINETUNE`,
`FINE_TUNE_AT`.
```bash
# 1. (Opcional) dataset sintetico para validar el pipeline (NO util como modelo real)
docker compose run --rm --no-deps api uv run python scripts/make_sample_dataset.py

# 2. Entrenar (descarga pesos ImageNet la 1a vez)
docker compose run --rm --no-deps -e EPOCHS_HEAD=10 -e EPOCHS_FINETUNE=10 \
  api uv run python scripts/train.py

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
`data/{train,val}/{damaged,intact}` (limpia destinos antes de copiar).

**Resultado:** con backbone congelado (15 epocas) el mejor modelo alcanza val_accuracy
~0.935, precision ~0.94, recall ~0.93. El fine-tuning (descongelar las ultimas capas)
degrada el recall a ~0.70 en este dataset (1840 imgs): al descongelar, las stats de
BatchNorm de ImageNet se desincronizan y desestabilizan el entrenamiento. Por eso
`EPOCHS_FINETUNE` es 0 por defecto; el `ModelCheckpoint` de la fase 2 usa
`initial_value_threshold` para no sobreescribir nunca un modelo peor que la fase 1.
