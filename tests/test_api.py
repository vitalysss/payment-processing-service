import httpx
import pytest

from app.main import app

pytestmark = pytest.mark.asyncio


async def request(
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    json: dict[str, str] | None = None,
) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.request(method, path, headers=headers, json=json)


async def test_health_endpoint() -> None:
    response = await request("GET", "/health", headers={"X-API-Key": "dev-api-key"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_health_endpoint_requires_api_key() -> None:
    response = await request("GET", "/health")

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or missing API key"}


async def test_payment_endpoint_requires_api_key() -> None:
    response = await request(
        "POST",
        "/api/v1/payments",
        headers={"Idempotency-Key": "order-42"},
        json={
            "amount": "100.00",
            "currency": "RUB",
            "webhook_url": "https://client.example/webhook",
        },
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or missing API key"}
