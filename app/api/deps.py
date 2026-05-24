from collections.abc import Generator

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.security import require_api_key
from app.db.session import SessionLocal


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def rate_limit(
    request: Request, response: Response, api_key: str = Depends(require_api_key)
) -> None:
    limiter = request.app.state.rate_limiter
    allowed, remaining, retry_after = limiter.hit(api_key)
    headers = {"X-RateLimit-Limit": str(limiter.limit), "X-RateLimit-Remaining": str(remaining)}
    response.headers.update(headers)
    if not allowed:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Limite de peticiones excedido.",
            headers={**headers, "Retry-After": str(retry_after)},
        )
