import httpx

from app.domain.entities import Payment
from app.domain.exceptions import WebhookDeliveryError
from app.infrastructure.config import settings


class HttpWebhookSender:
    async def send(self, payment: Payment) -> None:
        if payment.processed_at is None:
            raise ValueError("Cannot notify about an unprocessed payment")

        payload = {
            "payment_id": str(payment.id),
            "status": payment.status.value,
            "amount": str(payment.amount),
            "currency": payment.currency.value,
            "processed_at": payment.processed_at.isoformat(),
        }
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(settings.webhook_timeout_seconds)
            ) as client:
                response = await client.post(payment.webhook_url, json=payload)
                response.raise_for_status()
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            raise WebhookDeliveryError("Webhook delivery failed") from exc
