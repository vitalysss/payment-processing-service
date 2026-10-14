import asyncio
import logging

import httpx

from app.config import settings
from app.schemas import WebhookPayload

logger = logging.getLogger(__name__)


class WebhookDeliveryError(Exception):
    pass


async def deliver_webhook(url: str, payload: WebhookPayload) -> None:
    timeout = httpx.Timeout(settings.webhook_timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(1, settings.webhook_max_attempts + 1):
            try:
                response = await client.post(url, json=payload.model_dump(mode="json"))
                response.raise_for_status()
                return
            except (httpx.HTTPError, httpx.TimeoutException) as exc:
                if attempt >= settings.webhook_max_attempts:
                    raise WebhookDeliveryError(
                        f"Webhook delivery failed after {attempt} attempts"
                    ) from exc
                delay = 2 ** (attempt - 1)
                logger.warning(
                    "Webhook attempt %s/%s failed; retrying in %ss",
                    attempt,
                    settings.webhook_max_attempts,
                    delay,
                )
                await asyncio.sleep(delay)

