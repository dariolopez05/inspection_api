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
