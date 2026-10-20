from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.infrastructure.messaging.broker import RETRY_ATTEMPT_HEADER, retry_queue
from app.infrastructure.messaging.contracts import PaymentMessage
from app.infrastructure.messaging.publishers import RabbitRetryPublisher


def test_retry_queues_use_exponential_ttl_and_return_to_main_exchange() -> None:
    second_attempt = retry_queue(2)
    third_attempt = retry_queue(3)

    assert second_attempt.arguments["x-message-ttl"] == 1000
    assert third_attempt.arguments["x-message-ttl"] == 2000
    assert second_attempt.arguments["x-dead-letter-exchange"] == "payments"
    assert second_attempt.arguments["x-dead-letter-routing-key"] == "payments.new"


async def test_retry_publish_preserves_attempt_in_message_header() -> None:
    payment_id = uuid4()
    message = PaymentMessage(payment_id=payment_id)

    with patch(
        "app.infrastructure.messaging.publishers.broker.publish",
        new_callable=AsyncMock,
    ) as publish:
        await RabbitRetryPublisher().schedule(
            message,
            next_attempt=2,
            correlation_id=str(payment_id),
        )

    assert publish.await_args.kwargs["headers"] == {RETRY_ATTEMPT_HEADER: 2}
    assert publish.await_args.kwargs["persist"] is True
