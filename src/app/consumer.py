import asyncio
import logging
from datetime import UTC, datetime

from faststream import FastStream
from faststream.exceptions import RejectMessage
from sqlalchemy import select

from app.db import session_factory
from app.gateway import gateway
from app.messaging import (
    broker,
    declare_dead_letter_topology,
    payments_exchange,
    payments_queue,
)
from app.models import Payment, PaymentStatus
from app.outbox import publish_pending_events
from app.schemas import PaymentMessage, WebhookPayload
from app.webhook import WebhookDeliveryError, deliver_webhook

logger = logging.getLogger(__name__)
app = FastStream(broker)

_outbox_stop = asyncio.Event()
_outbox_task: asyncio.Task[None] | None = None


@broker.subscriber(payments_queue, payments_exchange)
async def process_payment(message: PaymentMessage) -> None:
    async with session_factory() as session:
        payment = await session.scalar(
            select(Payment).where(Payment.id == message.payment_id).with_for_update()
        )
        if payment is None:
            logger.error("Payment %s does not exist", message.payment_id)
            raise RejectMessage

        if payment.status == PaymentStatus.PENDING:
            payment.status = await gateway.process()
            payment.processed_at = datetime.now(UTC)
            await session.commit()

        if payment.processed_at is None:
            logger.error("Processed payment %s has no processed_at timestamp", payment.id)
            raise RejectMessage

        payload = WebhookPayload(
            payment_id=payment.id,
            status=payment.status,
            amount=payment.amount,
            currency=payment.currency,
            processed_at=payment.processed_at,
        )

    try:
        await deliver_webhook(payment.webhook_url, payload)
    except WebhookDeliveryError:
        logger.exception("Webhook permanently failed for payment %s", payment.id)
        raise RejectMessage from None


@app.after_startup
async def start_outbox_publisher() -> None:
    global _outbox_task
    await declare_dead_letter_topology()
    _outbox_stop.clear()
    _outbox_task = asyncio.create_task(publish_pending_events(_outbox_stop))


@app.on_shutdown
async def stop_outbox_publisher() -> None:
    _outbox_stop.set()
    if _outbox_task is not None:
        await _outbox_task
