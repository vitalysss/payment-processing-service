class IdempotencyConflictError(Exception):
    """An idempotency key was reused for a different request."""


class PaymentNotFoundError(Exception):
    """The requested payment does not exist."""


class PersistenceConflictError(Exception):
    """A database uniqueness constraint rejected a concurrent write."""


class WebhookDeliveryError(Exception):
    """A single webhook delivery attempt failed."""
