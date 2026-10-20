from datetime import datetime
from typing import Self
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

from app.application.outbox import PublishOutboxBatchService
from app.domain.entities import OutboxEvent


class FakeOutboxRepository:
    def __init__(self, event: OutboxEvent) -> None:
        self.event = event

    async def list_unpublished_locked(self, limit: int) -> list[OutboxEvent]:
        assert limit == 50
        return [self.event]

    async def mark_published(self, event_id: UUID, published_at: datetime) -> None:
        assert event_id == self.event.id
        self.event.published_at = published_at
        self.event.last_error = None

    async def record_failure(self, event_id: UUID, error: str) -> None:
        assert event_id == self.event.id
        self.event.attempts += 1
        self.event.last_error = error


class FakeUnitOfWork:
    def __init__(self, event: OutboxEvent) -> None:
        self.outbox = FakeOutboxRepository(event)
        self.payments = None
        self.committed = False

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        pass

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        pass


def event() -> OutboxEvent:
    return OutboxEvent.payment_created(uuid4())


async def test_outbox_marks_event_only_after_publish_confirmation() -> None:
    item = event()
    uow = FakeUnitOfWork(item)
    publisher = AsyncMock()
    service = PublishOutboxBatchService(lambda: uow, publisher)

    published = await service.execute()

    assert published is True
    assert item.published_at is not None
    publisher.publish.assert_awaited_once_with(item)
    assert uow.committed is True


async def test_outbox_records_publish_failure() -> None:
    item = event()
    uow = FakeUnitOfWork(item)
    publisher = AsyncMock()
    publisher.publish.side_effect = RuntimeError("RabbitMQ unavailable")
    service = PublishOutboxBatchService(lambda: uow, publisher)

    published = await service.execute()

    assert published is False
    assert item.attempts == 1
    assert item.last_error == "RabbitMQ unavailable"
    assert item.published_at is None
