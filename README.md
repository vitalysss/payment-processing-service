# Payment Processing Service

Асинхронный MVP сервиса приёма и обработки платежей. Платёж и событие для RabbitMQ
сохраняются в одной транзакции (Transactional Outbox), после чего consumer эмулирует
платёжный шлюз и отправляет результат на webhook клиента.

## Архитектура

```text
Client -> FastAPI -> PostgreSQL (payment + outbox in one transaction)
                          |
                    Outbox publisher
                          |
                      RabbitMQ
                          |
                       Consumer -> Payment gateway emulator
                          |
                       Client webhook
                          |
                    3 retries -> DLQ
```

- `POST /api/v1/payments` принимает платёж и отвечает `202 Accepted`.
- Повторный запрос с тем же `Idempotency-Key` и тем же телом возвращает исходный
  платёж и не создаёт второе событие. Если тело отличается, API отвечает `409 Conflict`.
- Outbox publisher читает события с `FOR UPDATE SKIP LOCKED`, публикует persistent
  сообщения и помечает их отправленными только после подтверждения RabbitMQ.
- Consumer ждёт 2–5 секунд, завершает платёж с вероятностью успеха 90% и отправляет
  webhook.
- Webhook выполняется до трёх раз с экспоненциальными паузами 1 и 2 секунды. После
  последней ошибки исходное сообщение отклоняется в `payments.dlq`.

## Запуск через Docker

Требуются Docker Desktop и Docker Compose v2.

```bash
docker compose up --build
```

Compose сначала поднимает PostgreSQL и RabbitMQ, затем применяет Alembic-миграции и
запускает API с consumer. После запуска доступны:

- Swagger UI: http://localhost:8001/docs
- RabbitMQ UI: http://localhost:15672 (`payments` / `payments`)
- API key по умолчанию: `dev-api-key`

Для собственного ключа создайте `.env` из `.env.example` или запустите Compose с
переменной `API_KEY`.

## Проверка API

Создать платёж:

```bash
curl -X POST http://localhost:8001/api/v1/payments \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-api-key" \
  -H "Idempotency-Key: order-42" \
  -d '{
    "amount": "1250.50",
    "currency": "RUB",
    "description": "Order #42",
    "metadata": {"order_id": 42},
    "webhook_url": "https://webhook.site/your-generated-id"
  }'
```

Получить состояние, подставив `payment_id` из ответа:

```bash
curl http://localhost:8001/api/v1/payments/PAYMENT_ID \
  -H "X-API-Key: dev-api-key"
```

Сразу после создания статус будет `pending`; после обработки — `succeeded` или
`failed`. Повторите POST с тем же `Idempotency-Key`, чтобы проверить идемпотентность:
`payment_id` останется прежним.

## Локальная разработка

```bash
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"
.venv/Scripts/ruff check .
.venv/Scripts/pytest -q
```

На Linux/macOS используйте `.venv/bin/...`. Интеграционные зависимости всё равно
удобнее запускать через Compose.

## Остановка

```bash
docker compose down
```

Чтобы также удалить тестовые данные PostgreSQL:

```bash
docker compose down -v
```

## Технологии

Python 3.12, FastAPI, Pydantic v2, async SQLAlchemy 2, PostgreSQL, Alembic,
RabbitMQ, FastStream, HTTPX, Docker Compose, Pytest и Ruff.
