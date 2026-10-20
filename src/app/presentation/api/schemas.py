import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, HttpUrl

from app.application.commands import CreatePaymentCommand
from app.domain.entities import Payment
from app.domain.enums import Currency, PaymentStatus


class PaymentCreate(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    currency: Currency
    description: str | None = Field(default=None, max_length=2000)
    metadata: dict[str, Any] = Field(default_factory=dict)
    webhook_url: HttpUrl

    def to_command(self, idempotency_key: str) -> CreatePaymentCommand:
        return CreatePaymentCommand(
            amount=self.amount,
            currency=self.currency,
            description=self.description,
            metadata=self.metadata,
            webhook_url=str(self.webhook_url),
            idempotency_key=idempotency_key,
        )


class PaymentAccepted(BaseModel):
    payment_id: uuid.UUID
    status: PaymentStatus
    created_at: datetime

    @classmethod
    def from_payment(cls, payment: Payment) -> "PaymentAccepted":
        return cls(
            payment_id=payment.id,
            status=payment.status,
            created_at=payment.created_at,
        )


class PaymentDetails(BaseModel):
    id: uuid.UUID
    amount: Decimal
    currency: Currency
    description: str | None
    metadata: dict[str, Any]
    status: PaymentStatus
    idempotency_key: str
    webhook_url: str
    created_at: datetime
    processed_at: datetime | None

    @classmethod
    def from_payment(cls, payment: Payment) -> "PaymentDetails":
        return cls(
            id=payment.id,
            amount=payment.amount,
            currency=payment.currency,
            description=payment.description,
            metadata=payment.metadata,
            status=payment.status,
            idempotency_key=payment.idempotency_key,
            webhook_url=payment.webhook_url,
            created_at=payment.created_at,
            processed_at=payment.processed_at,
        )
