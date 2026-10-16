from app.models import Payment


def test_payment_status_uses_public_lowercase_values() -> None:
    assert Payment.__table__.c.status.type.enums == ["pending", "succeeded", "failed"]
