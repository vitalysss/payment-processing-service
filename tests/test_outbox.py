from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.outbox import publish_batch


class FakeSession:
    def __init__(self, event: SimpleNamespace) -> None:
        self.event = event

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    def begin(self) -> "FakeSession":
        return self

    async def scalars(self, statement: object) -> list[SimpleNamespace]:
        return [self.event]


def event() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        aggregate_id=uuid4(),
        payload={"payment_id": str(uuid4())},
        attempts=0,
        last_error=None,
        published_at=None,
    )


async def test_outbox_publishes_persistent_message() -> None:
    item = event()
    publisher = AsyncMock()

    with (
        patch("app.outbox.session_factory", return_value=FakeSession(item)),
        patch("app.outbox.broker.publish", publisher),
    ):
        published = await publish_batch()

    assert published is True
    assert item.published_at is not None
    assert publisher.await_args.kwargs["persist"] is True


async def test_outbox_failure_is_recorded_without_busy_loop() -> None:
    item = event()

    with (
        patch("app.outbox.session_factory", return_value=FakeSession(item)),
        patch("app.outbox.broker.publish", new_callable=AsyncMock) as publisher,
    ):
        publisher.side_effect = RuntimeError("RabbitMQ unavailable")
        published = await publish_batch()

    assert published is False
    assert item.attempts == 1
    assert item.last_error == "RabbitMQ unavailable"
    assert item.published_at is None

