from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/health", headers={"X-API-Key": "dev-api-key"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_endpoint_requires_api_key() -> None:
    response = client.get("/health")

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or missing API key"}


def test_payment_endpoint_requires_api_key() -> None:
    response = client.post(
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
