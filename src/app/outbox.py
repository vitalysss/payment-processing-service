import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import select

from app.config import settings
from app.db import session_factory
from app.messaging import PAYMENTS_ROUTING_KEY, broker, payments_exchange
from app.models import OutboxEvent

logger = logging.getLogger(__name__)


async def publish_pending_events(stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            published_any = await publish_batch()
        except Exception:
            logger.exception("Outbox polling iteration failed")
            published_any = False
        if published_any:
            continue
        try:
            await asyncio.wait_for(
                stop.wait(), timeout=settings.outbox_poll_interval_seconds
            )
        except TimeoutError:
            pass


async def publish_batch(batch_size: int = 50) -> bool:
    async with session_factory() as session:
        async with session.begin():
            result = await session.scalars(
                select(OutboxEvent)
                .where(OutboxEvent.published_at.is_(None))
                .order_by(OutboxEvent.created_at)
                .with_for_update(skip_locked=True)
                .limit(batch_size)
            )
            events = list(result)
            for event in events:
                try:
                    await broker.publish(
                        event.payload,
                        exchange=payments_exchange,
                        routing_key=PAYMENTS_ROUTING_KEY,
                        message_id=str(event.id),
                        correlation_id=str(event.aggregate_id),
                        persistent=True,
                    )
                    event.published_at = datetime.now(UTC)
                    event.last_error = None
                except Exception as exc:
                    event.attempts += 1
                    event.last_error = str(exc)[:2000]
                    logger.exception("Could not publish outbox event %s", event.id)
        return bool(events)
