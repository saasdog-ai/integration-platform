"""Message queue factory."""

from app.core.config import get_settings
from app.core.logging import get_logger
from app.domain.interfaces import MessageQueueInterface

logger = get_logger(__name__)

# Singleton instance
_queue_instance: MessageQueueInterface | None = None


def get_message_queue() -> MessageQueueInterface:
    """
    Factory to create appropriate message queue based on configuration.

    Returns:
        MessageQueueInterface implementation based on cloud_provider setting.
    """
    global _queue_instance

    if _queue_instance is not None:
        return _queue_instance

    settings = get_settings()

    if settings.cloud_provider == "aws" and settings.queue_url:
        from app.infrastructure.queue.sqs_queue import SQSQueue

        _queue_instance = SQSQueue()
        logger.info("Using AWS SQS message queue")

    elif settings.cloud_provider == "azure":
        # Azure Queue Storage would go here
        # from app.infrastructure.queue.azure_queue import AzureQueue
        # _queue_instance = AzureQueue()
        logger.warning("Azure Queue not implemented, falling back to in-memory queue")
        from app.infrastructure.queue.memory_queue import InMemoryQueue

        _queue_instance = InMemoryQueue()

    elif settings.cloud_provider == "gcp":
        # GCP Pub/Sub would go here
        # from app.infrastructure.queue.gcp_queue import GCPPubSubQueue
        # _queue_instance = GCPPubSubQueue()
        logger.warning("GCP Pub/Sub not implemented, falling back to in-memory queue")
        from app.infrastructure.queue.memory_queue import InMemoryQueue

        _queue_instance = InMemoryQueue()

    else:
        # Default to in-memory queue for local development
        from app.infrastructure.queue.memory_queue import InMemoryQueue

        _queue_instance = InMemoryQueue()
        logger.info("Using in-memory message queue (local development mode)")

    return _queue_instance


def reset_queue() -> None:
    """Reset the queue instance (for testing)."""
    global _queue_instance
    _queue_instance = None
