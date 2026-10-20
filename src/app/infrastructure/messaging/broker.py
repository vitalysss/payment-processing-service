from faststream.rabbit import ExchangeType, RabbitBroker, RabbitExchange, RabbitQueue

from app.infrastructure.config import settings

PAYMENTS_ROUTING_KEY = "payments.new"
DLQ_ROUTING_KEY = "payments.dead"
RETRY_ATTEMPT_HEADER = "x-retry-attempt"

payments_exchange = RabbitExchange("payments", type=ExchangeType.DIRECT, durable=True)
retry_exchange = RabbitExchange("payments.retry", type=ExchangeType.DIRECT, durable=True)
dead_letter_exchange = RabbitExchange("payments.dlx", type=ExchangeType.DIRECT, durable=True)

payments_queue = RabbitQueue(
    "payments.new",
    routing_key=PAYMENTS_ROUTING_KEY,
    durable=True,
    arguments={
        "x-dead-letter-exchange": dead_letter_exchange.name,
        "x-dead-letter-routing-key": DLQ_ROUTING_KEY,
    },
)

dead_letter_queue = RabbitQueue(
    "payments.dlq",
    routing_key=DLQ_ROUTING_KEY,
    durable=True,
)


def retry_routing_key(attempt: int) -> str:
    return f"payments.retry.{attempt}"


def retry_queue(attempt: int) -> RabbitQueue:
    delay_seconds = settings.retry_base_delay_seconds * 2 ** (attempt - 2)
    return RabbitQueue(
        f"payments.retry.{delay_seconds}s",
        routing_key=retry_routing_key(attempt),
        durable=True,
        arguments={
            "x-message-ttl": delay_seconds * 1000,
            "x-dead-letter-exchange": payments_exchange.name,
            "x-dead-letter-routing-key": PAYMENTS_ROUTING_KEY,
        },
    )


broker = RabbitBroker(settings.rabbitmq_url, graceful_timeout=30)


async def declare_auxiliary_topology() -> None:
    dlx = await broker.declare_exchange(dead_letter_exchange)
    dlq = await broker.declare_queue(dead_letter_queue)
    await dlq.bind(dlx, routing_key=DLQ_ROUTING_KEY)

    retries = await broker.declare_exchange(retry_exchange)
    for attempt in range(2, settings.message_max_attempts + 1):
        queue = retry_queue(attempt)
        declared = await broker.declare_queue(queue)
        await declared.bind(retries, routing_key=retry_routing_key(attempt))
