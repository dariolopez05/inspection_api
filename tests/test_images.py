from httpx import AsyncClient

from app.main import app


async def test_image_requires_api_key(client: AsyncClient) -> None:
    response = await client.get("/inspections/1/image")
    assert response.status_code == 401


async def test_image_returns_presigned_url(
    client: AsyncClient, api_key: str, image_bytes: bytes
) -> None:
    await client.post(
        "/inspect",
        headers={"X-API-Key": api_key},
        data={"plate_number": "IMG001"},
        files={"file": ("car.jpg", image_bytes, "image/jpeg")},
    )
    history = await client.get("/history/IMG001", headers={"X-API-Key": api_key})
    inspection_id = history.json()["items"][0]["id"]  # InspectionResult no trae id; lo sacamos de history

    response = await client.get(
        f"/inspections/{inspection_id}/image", headers={"X-API-Key": api_key}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["url"] == "http://localhost:9000/signed-url"
    assert body["expires_in"] == 3600

    _, kwargs = app.state.s3_public.generate_presigned_url.call_args
    assert kwargs["Params"]["Bucket"] == "test-bucket"
    assert kwargs["Params"]["Key"] == "IMG001/1.jpg"


async def test_image_404_for_unknown_inspection(client: AsyncClient, api_key: str) -> None:
    response = await client.get("/inspections/9999/image", headers={"X-API-Key": api_key})
    assert response.status_code == 404
