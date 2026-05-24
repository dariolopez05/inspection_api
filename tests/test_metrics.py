from httpx import AsyncClient


async def test_metrics_open_and_exposes_counters(client: AsyncClient) -> None:
    response = await client.get("/metrics")
    assert response.status_code == 200
    body = response.text
    assert "http_requests_total" in body
    assert "inference_duration_seconds" in body
    assert "predictions_total" in body
