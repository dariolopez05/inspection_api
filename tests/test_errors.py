from httpx import AsyncClient


async def test_error_shape_on_404(client: AsyncClient, api_key: str) -> None:
    response = await client.get("/inspections/9999/image", headers={"X-API-Key": api_key})
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["status"] == 404
    assert error["path"] == "/inspections/9999/image"
    assert isinstance(error["message"], str)


async def test_error_shape_on_401(client: AsyncClient) -> None:
    response = await client.get("/history/ABC123")
    assert response.status_code == 401
    assert response.json()["error"]["status"] == 401


async def test_error_shape_on_validation(client: AsyncClient, api_key: str) -> None:
    response = await client.get(
        "/history/ABC123", headers={"X-API-Key": api_key}, params={"limit": 999}
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["status"] == 422
    assert "details" in error
