import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI

from app.api.routers import history, inspect
from app.core.config import get_settings
from app.core.security import require_api_key
from app.ml.classifier import load_classifier
from app.storage.s3 import ensure_bucket, get_s3_client

logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()

    model_path = Path(settings.model_path)
    if model_path.exists():
        app.state.model = load_classifier(model_path)
        logger.info("Modelo cargado desde %s", model_path)
    else:
        app.state.model = None
        logger.warning("Modelo no encontrado en %s; /inspect devolvera 503", model_path)

    app.state.s3 = get_s3_client()
    app.state.s3_bucket = settings.s3_bucket
    ensure_bucket(app.state.s3, app.state.s3_bucket)

    yield

    app.state.model = None
    app.state.s3 = None


app = FastAPI(title="Car Inspection API", version="0.1.0", lifespan=lifespan)
app.include_router(inspect.router, dependencies=[Depends(require_api_key)])
app.include_router(history.router, dependencies=[Depends(require_api_key)])


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}
