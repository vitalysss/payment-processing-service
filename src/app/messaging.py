from faststream.rabbit import ExchangeType, RabbitBroker, RabbitExchange, RabbitQueue

from app.config import settings

PAYMENTS_ROUTING_KEY = "payments.new"
DLQ_ROUTING_KEY = "payments.dead"

payments_exchange = RabbitExchange("payments", type=ExchangeType.DIRECT, durable=True)
dead_letter_exchange = RabbitExchange(
    "payments.dlx", type=ExchangeType.DIRECT, durable=True
)

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

broker = RabbitBroker(settings.rabbitmq_url, graceful_timeout=30)


async def declare_dead_letter_topology() -> None:
    exchange = await broker.declare_exchange(dead_letter_exchange)
    queue = await broker.declare_queue(dead_letter_queue)
    await queue.bind(exchange, routing_key=DLQ_ROUTING_KEY)

