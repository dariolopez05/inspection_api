from httpx import AsyncClient


async def test_history_requires_api_key(client: AsyncClient) -> None:
    response = await client.get("/history/ABC123")
    assert response.status_code == 401


async def test_history_returns_records(
    client: AsyncClient, api_key: str, image_bytes: bytes
) -> None:
    for _ in range(2):
        await client.post(
            "/inspect",
            headers={"X-API-Key": api_key},
            data={"plate_number": "HIST01"},
            files={"file": ("car.jpg", image_bytes, "image/jpeg")},
        )

    response = await client.get("/history/HIST01", headers={"X-API-Key": api_key})
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert all(item["plate_number"] == "HIST01" for item in body)
    assert body[0]["image_key"] is not None


async def test_history_empty_for_unknown_plate(client: AsyncClient, api_key: str) -> None:
    response = await client.get("/history/NOPE00", headers={"X-API-Key": api_key})
    assert response.status_code == 200
    assert response.json() == []
