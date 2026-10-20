from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.domain.entities import Payment
from app.domain.enums import Currency, PaymentStatus
from app.domain.exceptions import WebhookDeliveryError
from app.infrastructure.webhook import HttpWebhookSender


def processed_payment() -> Payment:
    payment = Payment.create(
        amount=Decimal("12.50"),
        currency=Currency.EUR,
        description=None,
        metadata={},
        idempotency_key="webhook-1",
        request_hash="hash",
        webhook_url="https://client.example/webhook",
    )
    payment.mark_processed(PaymentStatus.SUCCEEDED, datetime.now(UTC))
    return payment


async def test_webhook_adapter_performs_one_attempt() -> None:
    request = httpx.Request("POST", "https://client.example/webhook")
    response = httpx.Response(204, request=request)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as post:
        post.return_value = response
        await HttpWebhookSender().send(processed_payment())

    post.assert_awaited_once()


async def test_webhook_error_is_delegated_to_broker_retry() -> None:
    request = httpx.Request("POST", "https://client.example/webhook")
    response = httpx.Response(503, request=request)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as post:
        post.return_value = response
        with pytest.raises(WebhookDeliveryError):
            await HttpWebhookSender().send(processed_payment())

    post.assert_awaited_once()
