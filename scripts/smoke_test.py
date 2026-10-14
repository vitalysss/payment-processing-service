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
            with urllib.request.urlopen(f"{BASE_URL}/health", timeout=2) as response:
                if response.status == 200:
                    return
        except (OSError, urllib.error.URLError):
            time.sleep(1)
    raise TimeoutError("API did not become healthy")


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

    deadline = time.monotonic() + 30
    final: dict[str, object] = {}
    while time.monotonic() < deadline:
        status_code, final = request("GET", f"/api/v1/payments/{payment_id}")
        assert status_code == 200
        if final["status"] != "pending":
            break
        time.sleep(1)

    assert final["status"] in {"succeeded", "failed"}, final
    assert final["processed_at"] is not None
    print(f"Smoke test passed: payment_id={payment_id}, status={final['status']}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Smoke test failed: {exc}", file=sys.stderr)
        raise

