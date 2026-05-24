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
    assert body["total"] == 2
    assert len(body["items"]) == 2
    assert all(item["plate_number"] == "HIST01" for item in body["items"])
    assert body["items"][0]["image_key"] is not None


async def test_history_empty_for_unknown_plate(client: AsyncClient, api_key: str) -> None:
    response = await client.get("/history/NOPE00", headers={"X-API-Key": api_key})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 0
    assert body["items"] == []


async def test_history_pagination(client: AsyncClient, api_key: str, image_bytes: bytes) -> None:
    for _ in range(3):
        await client.post(
            "/inspect",
            headers={"X-API-Key": api_key},
            data={"plate_number": "PAGE01"},
            files={"file": ("car.jpg", image_bytes, "image/jpeg")},
        )

    response = await client.get(
        "/history/PAGE01", headers={"X-API-Key": api_key}, params={"limit": 2, "offset": 0}
    )
    body = response.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert body["limit"] == 2

    response = await client.get(
        "/history/PAGE01", headers={"X-API-Key": api_key}, params={"limit": 2, "offset": 2}
    )
    assert len(response.json()["items"]) == 1


async def test_history_rejects_bad_pagination(client: AsyncClient, api_key: str) -> None:
    response = await client.get(
        "/history/ABC123", headers={"X-API-Key": api_key}, params={"limit": 0}
    )
    assert response.status_code == 422
