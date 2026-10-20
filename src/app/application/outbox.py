import asyncio
import logging
from datetime import UTC, datetime

from app.domain.ports import EventPublisher, UnitOfWorkFactory

logger = logging.getLogger(__name__)


class PublishOutboxBatchService:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        publisher: EventPublisher,
    ) -> None:
        self._uow_factory = uow_factory
        self._publisher = publisher

    async def execute(self, batch_size: int = 50) -> bool:
        async with self._uow_factory() as uow:
            events = await uow.outbox.list_unpublished_locked(batch_size)
            published_any = False
            had_failure = False
            for event in events:
                try:
                    await self._publisher.publish(event)
                except Exception as exc:
                    had_failure = True
                    await uow.outbox.record_failure(event.id, str(exc)[:2000])
                else:
                    await uow.outbox.mark_published(event.id, datetime.now(UTC))
                    published_any = True
            await uow.commit()
            return published_any and not had_failure


async def run_outbox_publisher(
    service: PublishOutboxBatchService,
    stop: asyncio.Event,
    poll_interval_seconds: float,
) -> None:
    while not stop.is_set():
        try:
            published_any = await service.execute()
        except Exception:
            logger.exception("Outbox polling iteration failed")
            published_any = False
        if published_any:
            continue
        try:
            await asyncio.wait_for(stop.wait(), timeout=poll_interval_seconds)
        except TimeoutError:
            pass
