import hashlib
import json
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OutboxEvent, Payment
from app.schemas import PaymentCreate


def request_fingerprint(data: PaymentCreate) -> str:
    canonical = json.dumps(data.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


class IdempotencyConflictError(Exception):
    pass


async def create_payment(
    session: AsyncSession, data: PaymentCreate, idempotency_key: str
) -> Payment:
    existing = await session.scalar(
        select(Payment).where(Payment.idempotency_key == idempotency_key)
    )
    fingerprint = request_fingerprint(data)
    if existing is not None:
        if existing.request_hash != fingerprint:
            raise IdempotencyConflictError
        return existing

    payment = Payment(
        amount=data.amount,
        currency=data.currency,
        description=data.description,
        metadata_=data.metadata,
        idempotency_key=idempotency_key,
        request_hash=fingerprint,
        webhook_url=str(data.webhook_url),
    )
    session.add(payment)
    await session.flush()
    session.add(
        OutboxEvent(
            aggregate_id=payment.id,
            event_type="payment.created",
            payload={"payment_id": str(payment.id)},
        )
    )

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        concurrent = await session.scalar(
            select(Payment).where(Payment.idempotency_key == idempotency_key)
        )
        if concurrent is None:
            raise
        if concurrent.request_hash != fingerprint:
            raise IdempotencyConflictError from None
        return concurrent

    await session.refresh(payment)
    return payment


async def get_payment(session: AsyncSession, payment_id: uuid.UUID) -> Payment | None:
    return await session.get(Payment, payment_id)
