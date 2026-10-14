import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_api_key
from app.db import get_session
from app.schemas import PaymentAccepted, PaymentCreate, PaymentDetails
from app.services import IdempotencyConflictError, create_payment, get_payment

router = APIRouter(
    prefix="/api/v1/payments",
    tags=["payments"],
    dependencies=[Depends(require_api_key)],
)


@router.post("", response_model=PaymentAccepted, status_code=status.HTTP_202_ACCEPTED)
async def accept_payment(
    data: PaymentCreate,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PaymentAccepted:
    try:
        payment = await create_payment(session, data, idempotency_key)
    except IdempotencyConflictError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Idempotency-Key was already used with a different request",
        ) from None
    return PaymentAccepted(
        payment_id=payment.id,
        status=payment.status,
        created_at=payment.created_at,
    )


@router.get("/{payment_id}", response_model=PaymentDetails)
async def payment_details(
    payment_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PaymentDetails:
    payment = await get_payment(session, payment_id)
    if payment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")
    return PaymentDetails.from_payment(payment)
