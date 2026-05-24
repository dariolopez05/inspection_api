import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import request_id_var
from app.core.metrics import LATENCY, REQUESTS

logger = logging.getLogger("app.request")


async def request_context_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    token = request_id_var.set(request_id)
    start = time.perf_counter()
    try:
        response = await call_next(request)
        elapsed = time.perf_counter() - start
        response.headers["X-Request-ID"] = request_id

        route = request.scope.get("route")  # plantilla, no la ruta real (cardinalidad)
        path = route.path if route is not None else "__unmatched__"
        LATENCY.labels(request.method, path).observe(elapsed)
        REQUESTS.labels(request.method, path, response.status_code).inc()

        logger.info(
            "request",
            extra={
                "extra_fields": {
                    "method": request.method,
                    "path": path,
                    "status": response.status_code,
                    "latency_ms": round(elapsed * 1000, 1),
                }
            },
        )
        return response
    finally:
        request_id_var.reset(token)
