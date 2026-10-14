import asyncio
import random

from app.config import settings
from app.models import PaymentStatus


class PaymentGateway:
    async def process(self) -> PaymentStatus:
        delay = random.uniform(
            settings.gateway_min_delay_seconds,
            settings.gateway_max_delay_seconds,
        )
        await asyncio.sleep(delay)
        if random.random() < settings.gateway_success_rate:
            return PaymentStatus.SUCCEEDED
        return PaymentStatus.FAILED


gateway = PaymentGateway()

