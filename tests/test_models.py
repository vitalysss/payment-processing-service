from app.infrastructure.database.models import PaymentModel


def test_payment_status_uses_public_lowercase_values() -> None:
    assert PaymentModel.__table__.c.status.type.enums == ["pending", "succeeded", "failed"]
