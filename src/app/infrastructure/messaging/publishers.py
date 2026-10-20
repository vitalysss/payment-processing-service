from app.domain.entities import OutboxEvent
from app.infrastructure.messaging.broker import (
    PAYMENTS_ROUTING_KEY,
    RETRY_ATTEMPT_HEADER,
    broker,
    payments_exchange,
    retry_exchange,
    retry_routing_key,
)
from app.infrastructure.messaging.contracts import PaymentMessage


class RabbitEventPublisher:
    async def publish(self, event: OutboxEvent) -> None:
        await broker.publish(
            event.payload,
            exchange=payments_exchange,
            routing_key=PAYMENTS_ROUTING_KEY,
            message_id=str(event.id),
            correlation_id=str(event.aggregate_id),
            headers={RETRY_ATTEMPT_HEADER: 1},
            persist=True,
        )


class RabbitRetryPublisher:
    async def schedule(
        self,
        message: PaymentMessage,
        *,
        next_attempt: int,
        correlation_id: str,
    ) -> None:
        await broker.publish(
            message.model_dump(mode="json"),
            exchange=retry_exchange,
            routing_key=retry_routing_key(next_attempt),
            correlation_id=correlation_id,
            headers={RETRY_ATTEMPT_HEADER: next_attempt},
            persist=True,
        )
