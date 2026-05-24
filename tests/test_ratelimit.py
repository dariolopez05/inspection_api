from httpx import AsyncClient

from app.core.ratelimit import RateLimiter
from app.main import app


async def test_rate_limit_headers_present(client: AsyncClient, api_key: str) -> None:
    response = await client.get("/history/ABC123", headers={"X-API-Key": api_key})
    assert response.status_code == 200
    assert "x-ratelimit-limit" in response.headers
    assert "x-ratelimit-remaining" in response.headers


async def test_rate_limit_returns_429(client: AsyncClient, api_key: str) -> None:
    app.state.rate_limiter = RateLimiter(limit=2)
    headers = {"X-API-Key": api_key}

    assert (await client.get("/history/ABC123", headers=headers)).status_code == 200
    assert (await client.get("/history/ABC123", headers=headers)).status_code == 200

    blocked = await client.get("/history/ABC123", headers=headers)
    assert blocked.status_code == 429
    assert "retry-after" in blocked.headers
    assert blocked.json()["error"]["status"] == 429
