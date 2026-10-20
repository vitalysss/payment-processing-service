import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.domain.enums import Currency, PaymentStatus


@dataclass(slots=True)
class Payment:
    id: uuid.UUID
    amount: Decimal
    currency: Currency
    description: str | None
    metadata: dict[str, Any]
    status: PaymentStatus
    idempotency_key: str
    request_hash: str
    webhook_url: str
    created_at: datetime
    processed_at: datetime | None = None

    @classmethod
    def create(
        cls,
        *,
        amount: Decimal,
        currency: Currency,
        description: str | None,
        metadata: dict[str, Any],
        idempotency_key: str,
        request_hash: str,
        webhook_url: str,
    ) -> "Payment":
        return cls(
            id=uuid.uuid4(),
            amount=amount,
            currency=currency,
            description=description,
            metadata=metadata,
            status=PaymentStatus.PENDING,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            webhook_url=webhook_url,
            created_at=datetime.now(UTC),
        )

    def mark_processed(self, status: PaymentStatus, processed_at: datetime) -> None:
        if self.status is not PaymentStatus.PENDING:
            return
        self.status = status
        self.processed_at = processed_at


@dataclass(slots=True)
class OutboxEvent:
    id: uuid.UUID
    aggregate_id: uuid.UUID
    event_type: str
    payload: dict[str, Any]
    attempts: int = 0
    last_error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    published_at: datetime | None = None

    @classmethod
    def payment_created(cls, payment_id: uuid.UUID) -> "OutboxEvent":
        return cls(
            id=uuid.uuid4(),
            aggregate_id=payment_id,
            event_type="payment.created",
            payload={"payment_id": str(payment_id)},
        )
