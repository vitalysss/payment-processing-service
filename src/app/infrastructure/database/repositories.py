import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import OutboxEvent, Payment
from app.domain.enums import PaymentStatus
from app.domain.exceptions import PersistenceConflictError
from app.infrastructure.database.models import OutboxModel, PaymentModel


def payment_to_domain(model: PaymentModel) -> Payment:
    return Payment(
        id=model.id,
        amount=model.amount,
        currency=model.currency,
        description=model.description,
        metadata=model.metadata_,
        status=model.status,
        idempotency_key=model.idempotency_key,
        request_hash=model.request_hash,
        webhook_url=model.webhook_url,
        created_at=model.created_at,
        processed_at=model.processed_at,
    )


def outbox_to_domain(model: OutboxModel) -> OutboxEvent:
    return OutboxEvent(
        id=model.id,
        aggregate_id=model.aggregate_id,
        event_type=model.event_type,
        payload=model.payload,
        attempts=model.attempts,
        last_error=model.last_error,
        created_at=model.created_at,
        published_at=model.published_at,
    )


class SqlAlchemyPaymentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, payment_id: uuid.UUID) -> Payment | None:
        model = await self._session.get(PaymentModel, payment_id)
        return payment_to_domain(model) if model is not None else None

    async def get_by_idempotency_key(self, key: str) -> Payment | None:
        model = await self._session.scalar(
            select(PaymentModel).where(PaymentModel.idempotency_key == key)
        )
        return payment_to_domain(model) if model is not None else None

    async def add(self, payment: Payment) -> None:
        self._session.add(
            PaymentModel(
                id=payment.id,
                amount=payment.amount,
                currency=payment.currency,
                description=payment.description,
                metadata_=payment.metadata,
                status=payment.status,
                idempotency_key=payment.idempotency_key,
                request_hash=payment.request_hash,
                webhook_url=payment.webhook_url,
                created_at=payment.created_at,
                processed_at=payment.processed_at,
            )
        )
        # Flush the parent row before an outbox event referencing it is added.
        # The transaction is still open, so payment + outbox remain atomic.
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise PersistenceConflictError from exc

    async def update_if_pending(self, payment: Payment) -> Payment | None:
        model = await self._session.scalar(
            update(PaymentModel)
            .where(
                PaymentModel.id == payment.id,
                PaymentModel.status == PaymentStatus.PENDING,
            )
            .values(status=payment.status, processed_at=payment.processed_at)
            .returning(PaymentModel)
        )
        return payment_to_domain(model) if model is not None else None


class SqlAlchemyOutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, event: OutboxEvent) -> None:
        self._session.add(
            OutboxModel(
                id=event.id,
                aggregate_id=event.aggregate_id,
                event_type=event.event_type,
                payload=event.payload,
                attempts=event.attempts,
                last_error=event.last_error,
                created_at=event.created_at,
                published_at=event.published_at,
            )
        )

    async def list_unpublished_locked(self, limit: int) -> list[OutboxEvent]:
        models = await self._session.scalars(
            select(OutboxModel)
            .where(OutboxModel.published_at.is_(None))
            .order_by(OutboxModel.created_at)
            .with_for_update(skip_locked=True)
            .limit(limit)
        )
        return [outbox_to_domain(model) for model in models]

    async def mark_published(self, event_id: uuid.UUID, published_at: datetime) -> None:
        await self._session.execute(
            update(OutboxModel)
            .where(OutboxModel.id == event_id)
            .values(published_at=published_at, last_error=None)
        )

    async def record_failure(self, event_id: uuid.UUID, error: str) -> None:
        await self._session.execute(
            update(OutboxModel)
            .where(OutboxModel.id == event_id)
            .values(attempts=OutboxModel.attempts + 1, last_error=error)
        )
