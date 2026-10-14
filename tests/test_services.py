from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.models import Currency, Payment, PaymentStatus
from app.schemas import PaymentCreate
from app.services import IdempotencyConflictError, create_payment, request_fingerprint


def payment_data(amount: str = "10.50") -> PaymentCreate:
    return PaymentCreate(
        amount=amount,
        currency="USD",
        description="Test",
        metadata={"order": 1},
        webhook_url="https://client.example/webhook",
    )


def existing_payment(data: PaymentCreate) -> Payment:
    return Payment(
        id=uuid4(),
        amount=Decimal("10.50"),
        currency=Currency.USD,
        description="Test",
        metadata_={"order": 1},
        status=PaymentStatus.PENDING,
        idempotency_key="key-1",
        request_hash=request_fingerprint(data),
        webhook_url="https://client.example/webhook",
        created_at=datetime.now(UTC),
    )


class ExistingSession:
    def __init__(self, payment: Payment) -> None:
        self.payment = payment

    async def scalar(self, statement: object) -> Payment:
        return self.payment


async def test_same_idempotency_key_returns_existing_payment() -> None:
    data = payment_data()
    payment = existing_payment(data)

    result = await create_payment(ExistingSession(payment), data, "key-1")  # type: ignore[arg-type]

    assert result is payment


async def test_same_idempotency_key_rejects_different_payload() -> None:
    original = payment_data()
    payment = existing_payment(original)

    with pytest.raises(IdempotencyConflictError):
        await create_payment(
            ExistingSession(payment), payment_data("99.00"), "key-1"  # type: ignore[arg-type]
        )
