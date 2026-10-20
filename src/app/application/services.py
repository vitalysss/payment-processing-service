import hashlib
import json
import uuid
from datetime import UTC, datetime

from app.application.commands import CreatePaymentCommand
from app.domain.entities import OutboxEvent, Payment
from app.domain.exceptions import (
    IdempotencyConflictError,
    PaymentNotFoundError,
    PersistenceConflictError,
)
from app.domain.ports import PaymentGateway, UnitOfWorkFactory, WebhookSender


def request_fingerprint(command: CreatePaymentCommand) -> str:
    canonical = json.dumps(
        {
            "amount": str(command.amount),
            "currency": command.currency.value,
            "description": command.description,
            "metadata": command.metadata,
            "webhook_url": command.webhook_url,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


class CreatePaymentService:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, command: CreatePaymentCommand) -> Payment:
        fingerprint = request_fingerprint(command)
        async with self._uow_factory() as uow:
            existing = await uow.payments.get_by_idempotency_key(command.idempotency_key)
            if existing is not None:
                return self._validate_repeated_request(existing, fingerprint)

            payment = Payment.create(
                amount=command.amount,
                currency=command.currency,
                description=command.description,
                metadata=command.metadata,
                idempotency_key=command.idempotency_key,
                request_hash=fingerprint,
                webhook_url=command.webhook_url,
            )
            try:
                await uow.payments.add(payment)
                await uow.outbox.add(OutboxEvent.payment_created(payment.id))
                await uow.commit()
            except PersistenceConflictError:
                pass
            else:
                return payment

        # Another request may have committed the same key between SELECT and INSERT.
        async with self._uow_factory() as uow:
            concurrent = await uow.payments.get_by_idempotency_key(command.idempotency_key)
            if concurrent is None:
                raise PersistenceConflictError
            return self._validate_repeated_request(concurrent, fingerprint)

    @staticmethod
    def _validate_repeated_request(payment: Payment, fingerprint: str) -> Payment:
        if payment.request_hash != fingerprint:
            raise IdempotencyConflictError
        return payment


class GetPaymentService:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, payment_id: uuid.UUID) -> Payment | None:
        async with self._uow_factory() as uow:
            return await uow.payments.get(payment_id)


class ProcessPaymentService:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        gateway: PaymentGateway,
        webhook: WebhookSender,
    ) -> None:
        self._uow_factory = uow_factory
        self._gateway = gateway
        self._webhook = webhook

    async def execute(self, payment_id: uuid.UUID) -> Payment:
        # The read transaction ends before any external I/O starts.
        async with self._uow_factory() as uow:
            payment = await uow.payments.get(payment_id)

        if payment is None:
            raise PaymentNotFoundError

        if payment.processed_at is None:
            # A real gateway receives payment_id as its idempotency key.
            result = await self._gateway.process(payment.id)
            payment.mark_processed(result, datetime.now(UTC))

            # Status persistence is a separate short transaction with an atomic
            # `WHERE status = pending` guard. No row lock is held during gateway I/O.
            async with self._uow_factory() as uow:
                updated = await uow.payments.update_if_pending(payment)
                if updated is not None:
                    await uow.commit()
                    payment = updated
                else:
                    current = await uow.payments.get(payment.id)
                    if current is None:
                        raise PaymentNotFoundError
                    payment = current

        await self._webhook.send(payment)
        return payment
