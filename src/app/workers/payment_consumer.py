import asyncio
import logging

from faststream import FastStream
from faststream.exceptions import RejectMessage
from faststream.rabbit.annotations import RabbitMessage

from app.application.outbox import PublishOutboxBatchService, run_outbox_publisher
from app.application.services import ProcessPaymentService
from app.domain.exceptions import PaymentNotFoundError, WebhookDeliveryError
from app.infrastructure.config import settings
from app.infrastructure.database.uow import SqlAlchemyUnitOfWork
from app.infrastructure.gateway import SimulatedPaymentGateway
from app.infrastructure.messaging.broker import (
    RETRY_ATTEMPT_HEADER,
    broker,
    declare_auxiliary_topology,
    payments_exchange,
    payments_queue,
)
from app.infrastructure.messaging.contracts import PaymentMessage
from app.infrastructure.messaging.publishers import RabbitEventPublisher, RabbitRetryPublisher
from app.infrastructure.webhook import HttpWebhookSender

logger = logging.getLogger(__name__)
app = FastStream(broker)

_outbox_stop = asyncio.Event()
_outbox_task: asyncio.Task[None] | None = None
_retry_publisher = RabbitRetryPublisher()


@broker.subscriber(payments_queue, payments_exchange)
async def process_payment(message: PaymentMessage, raw_message: RabbitMessage) -> None:
    attempt = int(raw_message.headers.get(RETRY_ATTEMPT_HEADER, 1))
    service = ProcessPaymentService(
        SqlAlchemyUnitOfWork,
        SimulatedPaymentGateway(),
        HttpWebhookSender(),
    )
    try:
        await service.execute(message.payment_id)
    except PaymentNotFoundError:
        logger.error("Payment %s does not exist", message.payment_id)
        raise RejectMessage from None
    except WebhookDeliveryError:
        if attempt >= settings.message_max_attempts:
            logger.exception(
                "Payment %s failed after %s queue attempts; routing to DLQ",
                message.payment_id,
                attempt,
            )
            raise RejectMessage from None

        next_attempt = attempt + 1
        logger.warning(
            "Payment %s webhook attempt %s/%s failed; scheduling queue attempt %s",
            message.payment_id,
            attempt,
            settings.message_max_attempts,
            next_attempt,
        )
        # Publish-confirm happens before FastStream acknowledges the original.
        # If publishing fails, the exception leaves the handler and RabbitMQ
        # requeues the original delivery instead of losing it.
        await _retry_publisher.schedule(
            message,
            next_attempt=next_attempt,
            correlation_id=raw_message.correlation_id,
        )


@app.after_startup
async def start_background_services() -> None:
    global _outbox_task
    await declare_auxiliary_topology()
    _outbox_stop.clear()
    publisher = PublishOutboxBatchService(SqlAlchemyUnitOfWork, RabbitEventPublisher())
    _outbox_task = asyncio.create_task(
        run_outbox_publisher(
            publisher,
            _outbox_stop,
            settings.outbox_poll_interval_seconds,
        )
    )


@app.on_shutdown
async def stop_background_services() -> None:
    _outbox_stop.set()
    if _outbox_task is not None:
        await _outbox_task
