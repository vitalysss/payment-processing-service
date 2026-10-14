from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.models import Currency
from app.schemas import PaymentCreate


def test_payment_create_accepts_supported_currency() -> None:
    payment = PaymentCreate(
        amount="100.50",
        currency="RUB",
        description="Order #42",
        metadata={"order_id": 42},
        webhook_url="https://client.example/webhooks/payment",
    )

    assert payment.amount == Decimal("100.50")
    assert payment.currency is Currency.RUB


@pytest.mark.parametrize("amount", ["0", "-1", "1.001"])
def test_payment_create_rejects_invalid_amount(amount: str) -> None:
    with pytest.raises(ValidationError):
        PaymentCreate(
            amount=amount,
            currency="USD",
            webhook_url="https://client.example/webhook",
        )


def test_payment_create_rejects_unknown_currency() -> None:
    with pytest.raises(ValidationError):
        PaymentCreate(
            amount="1.00",
            currency="GBP",
            webhook_url="https://client.example/webhook",
        )

