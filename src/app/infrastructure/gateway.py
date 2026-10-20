import asyncio
import random
import uuid

from app.domain.enums import PaymentStatus
from app.infrastructure.config import settings


class SimulatedPaymentGateway:
    async def process(self, payment_id: uuid.UUID) -> PaymentStatus:
        # payment_id is the idempotency key a real gateway adapter would forward.
        del payment_id
        delay = random.uniform(
            settings.gateway_min_delay_seconds,
            settings.gateway_max_delay_seconds,
        )
        await asyncio.sleep(delay)
        if random.random() < settings.gateway_success_rate:
            return PaymentStatus.SUCCEEDED
        return PaymentStatus.FAILED
