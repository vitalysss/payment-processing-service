import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.application.services import CreatePaymentService, GetPaymentService
from app.domain.exceptions import IdempotencyConflictError
from app.infrastructure.database.uow import SqlAlchemyUnitOfWork
from app.presentation.api.auth import require_api_key
from app.presentation.api.schemas import PaymentAccepted, PaymentCreate, PaymentDetails

router = APIRouter(
    prefix="/api/v1/payments",
    tags=["payments"],
    dependencies=[Depends(require_api_key)],
)


@router.post("", response_model=PaymentAccepted, status_code=status.HTTP_202_ACCEPTED)
async def accept_payment(
    data: PaymentCreate,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)],
) -> PaymentAccepted:
    service = CreatePaymentService(SqlAlchemyUnitOfWork)
    try:
        payment = await service.execute(data.to_command(idempotency_key))
    except IdempotencyConflictError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Idempotency-Key was already used with a different request",
        ) from None
    return PaymentAccepted.from_payment(payment)


@router.get("/{payment_id}", response_model=PaymentDetails)
async def payment_details(payment_id: uuid.UUID) -> PaymentDetails:
    payment = await GetPaymentService(SqlAlchemyUnitOfWork).execute(payment_id)
    if payment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")
    return PaymentDetails.from_payment(payment)
