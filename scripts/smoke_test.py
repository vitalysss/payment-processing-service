import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

BASE_URL = os.getenv("SMOKE_BASE_URL", "http://localhost:8001")
API_KEY = os.getenv("SMOKE_API_KEY", "dev-api-key")
WEBHOOK_URL = os.getenv("SMOKE_WEBHOOK_URL", "http://webhook-sink:9000/webhook")
FAILURE_WEBHOOK_URL = os.getenv(
    "SMOKE_FAILURE_WEBHOOK_URL", "http://webhook-sink:9000/fail"
)
RABBITMQ_MANAGEMENT_URL = os.getenv(
    "SMOKE_RABBITMQ_MANAGEMENT_URL",
    "http://localhost:15672/api/queues/%2F/payments.dlq",
)
RABBITMQ_USER = os.getenv("SMOKE_RABBITMQ_USER", "payments")
RABBITMQ_PASSWORD = os.getenv("SMOKE_RABBITMQ_PASSWORD", "payments")


def request(
    method: str,
    path: str,
    *,
    body: dict[str, object] | None = None,
    idempotency_key: str | None = None,
) -> tuple[int, dict[str, object]]:
    headers = {"X-API-Key": API_KEY}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key

    req = urllib.request.Request(
        f"{BASE_URL}{path}", data=data, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def wait_for_api(timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            health_request = urllib.request.Request(
                f"{BASE_URL}/health", headers={"X-API-Key": API_KEY}
            )
            with urllib.request.urlopen(health_request, timeout=2) as response:
                if response.status == 200:
                    return
        except (OSError, urllib.error.URLError):
            time.sleep(1)
    raise TimeoutError("API did not become healthy")


def dlq_message_count() -> int:
    credentials = base64.b64encode(
        f"{RABBITMQ_USER}:{RABBITMQ_PASSWORD}".encode()
    ).decode()
    req = urllib.request.Request(
        RABBITMQ_MANAGEMENT_URL,
        headers={"Authorization": f"Basic {credentials}"},
    )
    with urllib.request.urlopen(req, timeout=5) as response:
        queue = json.loads(response.read())
    return int(queue.get("messages", 0))


def wait_for_final_status(payment_id: object, timeout: float = 30) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    final: dict[str, object] = {}
    while time.monotonic() < deadline:
        status_code, final = request("GET", f"/api/v1/payments/{payment_id}")
        assert status_code == 200
        if final["status"] != "pending":
            return final
        time.sleep(1)
    raise TimeoutError(f"Payment {payment_id} was not processed")


def main() -> None:
    wait_for_api()
    key = f"smoke-{uuid.uuid4()}"
    body: dict[str, object] = {
        "amount": "42.00",
        "currency": "USD",
        "description": "Automated Docker smoke test",
        "metadata": {"source": "smoke-test"},
        "webhook_url": WEBHOOK_URL,
    }

    status_code, created = request("POST", "/api/v1/payments", body=body, idempotency_key=key)
    assert status_code == 202, (status_code, created)
    payment_id = created["payment_id"]

    status_code, repeated = request("POST", "/api/v1/payments", body=body, idempotency_key=key)
    assert status_code == 202
    assert repeated["payment_id"] == payment_id

    conflicting = {**body, "amount": "99.00"}
    status_code, _ = request(
        "POST", "/api/v1/payments", body=conflicting, idempotency_key=key
    )
    assert status_code == 409

    final = wait_for_final_status(payment_id)
    assert final["status"] in {"succeeded", "failed"}, final
    assert final["processed_at"] is not None

    dlq_before = dlq_message_count()
    failed_webhook_body = {
        **body,
        "description": "Automated DLQ smoke test",
        "webhook_url": FAILURE_WEBHOOK_URL,
    }
    status_code, failed_webhook_payment = request(
        "POST",
        "/api/v1/payments",
        body=failed_webhook_body,
        idempotency_key=f"smoke-dlq-{uuid.uuid4()}",
    )
    assert status_code == 202, (status_code, failed_webhook_payment)
    failed_webhook_payment_id = failed_webhook_payment["payment_id"]
    wait_for_final_status(failed_webhook_payment_id)

    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if dlq_message_count() >= dlq_before + 1:
            break
        time.sleep(1)
    else:
        raise TimeoutError("Failed webhook message did not reach payments.dlq")

    print(
        "Smoke test passed: "
        f"payment_id={payment_id}, status={final['status']}, "
        f"dlq_payment_id={failed_webhook_payment_id}"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Smoke test failed: {exc}", file=sys.stderr)
        raise
