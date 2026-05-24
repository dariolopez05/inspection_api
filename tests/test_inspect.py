from httpx import AsyncClient

from app.main import app


async def test_inspect_requires_api_key(client: AsyncClient, image_bytes: bytes) -> None:
    response = await client.post(
        "/inspect",
        data={"plate_number": "ABC123"},
        files={"file": ("car.jpg", image_bytes, "image/jpeg")},
    )
    assert response.status_code == 401


async def test_inspect_ok(client: AsyncClient, api_key: str, image_bytes: bytes) -> None:
    response = await client.post(
        "/inspect",
        headers={"X-API-Key": api_key},
        data={"plate_number": "ABC123"},
        files={"file": ("car.jpg", image_bytes, "image/jpeg")},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["plate_number"] == "ABC123"
    assert body["is_damaged"] is True
    assert body["confidence"] == 0.9876
    assert body["image_key"] == "ABC123/1.jpg"


async def test_inspect_uploads_to_s3(client: AsyncClient, api_key: str, image_bytes: bytes) -> None:
    await client.post(
        "/inspect",
        headers={"X-API-Key": api_key},
        data={"plate_number": "ZZZ999"},
        files={"file": ("car.jpg", image_bytes, "image/jpeg")},
    )
    assert app.state.s3.put_object.called
    _, kwargs = app.state.s3.put_object.call_args
    assert kwargs["Bucket"] == "test-bucket"
    assert kwargs["Key"] == "ZZZ999/1.jpg"
    assert kwargs["ContentType"] == "image/jpeg"


async def test_inspect_rejects_non_image(client: AsyncClient, api_key: str) -> None:
    response = await client.post(
        "/inspect",
        headers={"X-API-Key": api_key},
        data={"plate_number": "ABC123"},
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 400
