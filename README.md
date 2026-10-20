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
               retry queues (1s -> 2s) -> DLQ
```

Код разделён на слои, зависимости направлены внутрь:

```text
src/app/
├── domain/          # сущности, enum, исключения и абстрактные порты
├── application/     # use cases: create/get/process payment, outbox publisher
├── infrastructure/  # SQLAlchemy, Unit of Work, RabbitMQ, gateway, HTTP webhook
├── presentation/    # FastAPI-схемы, авторизация и routes
└── workers/         # тонкий FastStream consumer
```

Домен и application-слой не импортируют FastAPI, FastStream или SQLAlchemy. Работа с
БД скрыта за repository-портами и `UnitOfWork`; инфраструктура реализует эти порты.

- `POST /api/v1/payments` принимает платёж и отвечает `202 Accepted`.
- Все endpoint'ы API, включая `/health`, требуют заголовок `X-API-Key`.
- Повторный запрос с тем же `Idempotency-Key` и тем же телом возвращает исходный
  платёж и не создаёт второе событие. Если тело отличается, API отвечает `409 Conflict`.
- Outbox publisher читает события с `FOR UPDATE SKIP LOCKED`, публикует persistent
  сообщения и помечает их отправленными только после подтверждения RabbitMQ.
- Consumer только преобразует входящее сообщение и вызывает application service.
  Use case читает платёж в короткой транзакции, закрывает её, вызывает шлюз и затем
  сохраняет результат отдельной условной операцией `UPDATE ... WHERE status = pending`.
  Во время ожидания шлюза 2–5 секунд и webhook транзакция и row lock не удерживаются.
- Одна доставка сообщения выполняет только одну попытку webhook. При ошибке сообщение
  с увеличенным номером попытки публикуется в durable retry-очередь. RabbitMQ выдерживает
  задержки 1 и 2 секунды через TTL и возвращает сообщение в `payments.new`. После третьей
  отдельной обработки сообщение отклоняется и маршрутизируется через `payments.dlx` в
  `payments.dlq`.

### Гарантии и границы транзакций

- Создание `payments` и `outbox` выполняется одной транзакцией PostgreSQL.
- Публикация исходного события имеет семантику at-least-once; повторная доставка не
  запускает шлюз для уже завершённого платежа.
- Retry-сообщение подтверждается RabbitMQ до acknowledgement исходной доставки. Если
  повторная публикация не удалась, исходное сообщение будет requeue, а не потеряно.
- ID платежа передаётся в gateway-порт как idempotency key для адаптера реального шлюза.
- Exactly-once между независимыми системами не заявляется; получатель webhook также
  должен обрабатывать повтор по `payment_id` идемпотентно.

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

## Автоматический smoke-тест

Профиль `test` добавляет внутренний webhook-приёмник. Скрипт проверяет создание и
обработку платежа, повтор с тем же ключом, конфликт при изменённом теле, три
неудачные попытки доставки webhook и появление сообщения в `payments.dlq`:

```bash
docker compose --profile test up -d --build
python scripts/smoke_test.py
docker compose --profile test down -v
```

Тот же сценарий автоматически выполняется в GitHub Actions.

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
