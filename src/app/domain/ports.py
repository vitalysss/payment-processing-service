import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Protocol, Self

from app.domain.entities import OutboxEvent, Payment
from app.domain.enums import PaymentStatus


class PaymentRepository(Protocol):
    async def get(self, payment_id: uuid.UUID) -> Payment | None: ...

    async def get_by_idempotency_key(self, key: str) -> Payment | None: ...

    async def add(self, payment: Payment) -> None: ...

    async def update_if_pending(self, payment: Payment) -> Payment | None: ...


class OutboxRepository(Protocol):
    async def add(self, event: OutboxEvent) -> None: ...

    async def list_unpublished_locked(self, limit: int) -> list[OutboxEvent]: ...

    async def mark_published(self, event_id: uuid.UUID, published_at: datetime) -> None: ...

    async def record_failure(self, event_id: uuid.UUID, error: str) -> None: ...


class UnitOfWork(Protocol):
    payments: PaymentRepository
    outbox: OutboxRepository

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


UnitOfWorkFactory = Callable[[], UnitOfWork]


class PaymentGateway(Protocol):
    async def process(self, payment_id: uuid.UUID) -> PaymentStatus: ...


class WebhookSender(Protocol):
    async def send(self, payment: Payment) -> None: ...


class EventPublisher(Protocol):
    async def publish(self, event: OutboxEvent) -> None: ...
