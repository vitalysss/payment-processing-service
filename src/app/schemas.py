import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_serializer

from app.models import Currency, PaymentStatus


class PaymentCreate(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    currency: Currency
    description: str | None = Field(default=None, max_length=2000)
    metadata: dict[str, Any] = Field(default_factory=dict)
    webhook_url: HttpUrl


class PaymentAccepted(BaseModel):
    payment_id: uuid.UUID
    status: PaymentStatus
    created_at: datetime


class PaymentDetails(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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
    def from_payment(cls, payment: object) -> "PaymentDetails":
        return cls.model_validate(
            {
                "id": payment.id,
                "amount": payment.amount,
                "currency": payment.currency,
                "description": payment.description,
                "metadata": payment.metadata_,
                "status": payment.status,
                "idempotency_key": payment.idempotency_key,
                "webhook_url": payment.webhook_url,
                "created_at": payment.created_at,
                "processed_at": payment.processed_at,
            }
        )


class PaymentMessage(BaseModel):
    payment_id: uuid.UUID


class WebhookPayload(BaseModel):
    payment_id: uuid.UUID
    status: PaymentStatus
    amount: Decimal
    currency: Currency
    processed_at: datetime

    @field_serializer("amount")
    def serialize_amount(self, value: Decimal) -> str:
        return str(value)

