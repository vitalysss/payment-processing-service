from datetime import UTC, datetime
from decimal import Decimal
from typing import Self
from uuid import UUID

import pytest

from app.application.commands import CreatePaymentCommand
from app.application.services import CreatePaymentService, ProcessPaymentService
from app.domain.entities import OutboxEvent, Payment
from app.domain.enums import Currency, PaymentStatus
from app.domain.exceptions import IdempotencyConflictError


def command(amount: str = "10.50") -> CreatePaymentCommand:
    return CreatePaymentCommand(
        amount=Decimal(amount),
        currency=Currency.USD,
        description="Test",
        metadata={"order": 1},
        webhook_url="https://client.example/webhook",
        idempotency_key="key-1",
    )


class FakePaymentRepository:
    def __init__(self, store: dict[UUID, Payment]) -> None:
        self.store = store

    async def get(self, payment_id: UUID) -> Payment | None:
        return self.store.get(payment_id)

    async def get_by_idempotency_key(self, key: str) -> Payment | None:
        return next((item for item in self.store.values() if item.idempotency_key == key), None)

    async def add(self, payment: Payment) -> None:
        self.store[payment.id] = payment

    async def update_if_pending(self, payment: Payment) -> Payment | None:
        current = self.store.get(payment.id)
        if current is None or current.status is not PaymentStatus.PENDING:
            return None
        self.store[payment.id] = payment
        return payment


class FakeOutboxRepository:
    def __init__(self, events: list[OutboxEvent]) -> None:
        self.events = events

    async def add(self, event: OutboxEvent) -> None:
        self.events.append(event)


class FakeUnitOfWork:
    def __init__(
        self,
        store: dict[UUID, Payment],
        events: list[OutboxEvent],
        active: list["FakeUnitOfWork"],
    ) -> None:
        self.payments = FakePaymentRepository(store)
        self.outbox = FakeOutboxRepository(events)
        self._active = active

    async def __aenter__(self) -> Self:
        self._active.append(self)
        return self

    async def __aexit__(self, *args: object) -> None:
        self._active.remove(self)

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass


class FakeUowFactory:
    def __init__(self) -> None:
        self.store: dict[UUID, Payment] = {}
        self.events: list[OutboxEvent] = []
        self.active: list[FakeUnitOfWork] = []

    def __call__(self) -> FakeUnitOfWork:
        return FakeUnitOfWork(self.store, self.events, self.active)


class AssertingGateway:
    def __init__(self, factory: FakeUowFactory) -> None:
        self.factory = factory
        self.calls = 0

    async def process(self, payment_id: UUID) -> PaymentStatus:
        assert not self.factory.active, "gateway called inside database transaction"
        assert payment_id in self.factory.store
        self.calls += 1
        return PaymentStatus.SUCCEEDED


class AssertingWebhook:
    def __init__(self, factory: FakeUowFactory) -> None:
        self.factory = factory
        self.calls = 0

    async def send(self, payment: Payment) -> None:
        assert not self.factory.active, "webhook called inside database transaction"
        assert payment.processed_at is not None
        self.calls += 1


async def test_create_is_idempotent_and_writes_outbox() -> None:
    factory = FakeUowFactory()
    service = CreatePaymentService(factory)

    first = await service.execute(command())
    repeated = await service.execute(command())

    assert repeated.id == first.id
    assert len(factory.store) == 1
    assert len(factory.events) == 1
    assert factory.events[0].aggregate_id == first.id


async def test_same_key_rejects_different_payload() -> None:
    factory = FakeUowFactory()
    service = CreatePaymentService(factory)
    await service.execute(command())

    with pytest.raises(IdempotencyConflictError):
        await service.execute(command("99.00"))


async def test_processing_performs_external_io_outside_transaction() -> None:
    factory = FakeUowFactory()
    payment = Payment.create(
        amount=Decimal("12.50"),
        currency=Currency.EUR,
        description=None,
        metadata={},
        idempotency_key="process-1",
        request_hash="hash",
        webhook_url="https://client.example/webhook",
    )
    factory.store[payment.id] = payment
    gateway = AssertingGateway(factory)
    webhook = AssertingWebhook(factory)

    result = await ProcessPaymentService(factory, gateway, webhook).execute(payment.id)

    assert result.status is PaymentStatus.SUCCEEDED
    assert result.processed_at is not None
    assert gateway.calls == 1
    assert webhook.calls == 1


async def test_redelivery_does_not_call_gateway_twice() -> None:
    factory = FakeUowFactory()
    payment = Payment.create(
        amount=Decimal("5.00"),
        currency=Currency.RUB,
        description=None,
        metadata={},
        idempotency_key="processed-1",
        request_hash="hash",
        webhook_url="https://client.example/webhook",
    )
    payment.mark_processed(PaymentStatus.SUCCEEDED, datetime.now(UTC))
    factory.store[payment.id] = payment
    gateway = AssertingGateway(factory)
    webhook = AssertingWebhook(factory)

    await ProcessPaymentService(factory, gateway, webhook).execute(payment.id)

    assert gateway.calls == 0
    assert webhook.calls == 1
