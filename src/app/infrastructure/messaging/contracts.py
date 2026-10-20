import uuid

from pydantic import BaseModel


class PaymentMessage(BaseModel):
    payment_id: uuid.UUID
