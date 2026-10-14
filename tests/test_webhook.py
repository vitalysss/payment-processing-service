from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest

from app.models import Currency, PaymentStatus
from app.schemas import WebhookPayload
from app.webhook import WebhookDeliveryError, deliver_webhook


def payload() -> WebhookPayload:
    return WebhookPayload(
        payment_id=uuid4(),
        status=PaymentStatus.SUCCEEDED,
        amount=Decimal("12.50"),
        currency=Currency.EUR,
        processed_at=datetime.now(UTC),
    )


async def test_webhook_retries_then_succeeds() -> None:
    request = httpx.Request("POST", "https://client.example/webhook")
    failure = httpx.Response(503, request=request)
    success = httpx.Response(204, request=request)

    with (
        patch("app.webhook.settings.webhook_max_attempts", 3),
        patch("app.webhook.asyncio.sleep", new_callable=AsyncMock),
        patch("httpx.AsyncClient.post", new_callable=AsyncMock) as post,
    ):
        post.side_effect = [failure, success]
        await deliver_webhook(str(request.url), payload())

    assert post.await_count == 2


async def test_webhook_raises_after_three_failures() -> None:
    request = httpx.Request("POST", "https://client.example/webhook")
    failure = httpx.Response(503, request=request)

    with (
        patch("app.webhook.settings.webhook_max_attempts", 3),
        patch("app.webhook.asyncio.sleep", new_callable=AsyncMock),
        patch("httpx.AsyncClient.post", new_callable=AsyncMock) as post,
    ):
        post.return_value = failure
        with pytest.raises(WebhookDeliveryError):
            await deliver_webhook(str(request.url), payload())

    assert post.await_count == 3
