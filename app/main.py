import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Response

from app.api.deps import rate_limit
from app.api.routers import history, images, inspect
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.logging import setup_logging
from app.core.metrics import render
from app.core.middleware import request_context_middleware
from app.core.ratelimit import RateLimiter
from app.core.security import require_api_key
from app.ml.classifier import load_classifier
from app.storage.s3 import ensure_bucket, get_s3_client

setup_logging()
logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()

    model_path = Path(settings.model_path)
    if model_path.exists():
        app.state.model = load_classifier(model_path)
        logger.info("modelo cargado", extra={"extra_fields": {"model_path": str(model_path)}})
    else:
        app.state.model = None
        logger.warning(
            "modelo no encontrado, /inspect devolvera 503",
            extra={"extra_fields": {"model_path": str(model_path)}},
        )

    app.state.s3 = get_s3_client()
    app.state.s3_bucket = settings.s3_bucket
    ensure_bucket(app.state.s3, app.state.s3_bucket)
    # cliente para firmar presigned URLs con el host que ve el cliente (no el host interno de docker)
    app.state.s3_public = get_s3_client(settings.s3_public_endpoint_url)

    app.state.rate_limiter = RateLimiter(settings.rate_limit_per_minute)

    yield

    app.state.model = None
    app.state.s3 = None
    app.state.s3_public = None


app = FastAPI(title="Car Inspection API", version="0.1.0", lifespan=lifespan)
app.middleware("http")(request_context_middleware)
register_error_handlers(app)
protected = [Depends(require_api_key), Depends(rate_limit)]
app.include_router(inspect.router, dependencies=protected)
app.include_router(history.router, dependencies=protected)
app.include_router(images.router, dependencies=protected)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics", tags=["meta"])
def metrics() -> Response:
    body, content_type = render()
    return Response(content=body, media_type=content_type)
