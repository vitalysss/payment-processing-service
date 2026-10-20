from types import TracebackType

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.exceptions import PersistenceConflictError
from app.infrastructure.database.repositories import (
    SqlAlchemyOutboxRepository,
    SqlAlchemyPaymentRepository,
)
from app.infrastructure.database.session import session_factory


class SqlAlchemyUnitOfWork:
    def __init__(
        self,
        factory: async_sessionmaker[AsyncSession] = session_factory,
    ) -> None:
        self._factory = factory
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> "SqlAlchemyUnitOfWork":
        self._session = self._factory()
        self.payments = SqlAlchemyPaymentRepository(self._session)
        self.outbox = SqlAlchemyOutboxRepository(self._session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._session is None:
            return
        if exc_type is not None:
            await self._session.rollback()
        await self._session.close()

    async def commit(self) -> None:
        assert self._session is not None
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise PersistenceConflictError from exc

    async def rollback(self) -> None:
        assert self._session is not None
        await self._session.rollback()
