"""AWS SQS message queue implementation."""

import json
from typing import Any

from app.core.config import get_settings
from app.core.exceptions import QueueError
from app.core.logging import get_logger
from app.domain.entities import QueueMessage
from app.domain.interfaces import MessageQueueInterface

logger = get_logger(__name__)

# Default timeouts for SQS operations (in seconds)
DEFAULT_CONNECT_TIMEOUT = 10  # Time to establish connection
DEFAULT_READ_TIMEOUT = 30  # Time to wait for response (should be > WaitTimeSeconds)


class SQSQueue(MessageQueueInterface):
    """AWS SQS message queue implementation."""

    def __init__(
        self,
        queue_url: str | None = None,
        region: str | None = None,
        endpoint_url: str | None = None,
    ) -> None:
        """
        Initialize SQS queue.

        Args:
            queue_url: SQS queue URL. If not provided, uses settings.
            region: AWS region. If not provided, uses settings.
            endpoint_url: Custom endpoint URL (for localstack).
        """
        settings = get_settings()
        self._queue_url = queue_url or settings.queue_url
        self._region = region or settings.aws_region
        self._endpoint_url = endpoint_url or settings.aws_endpoint_url
        self._client = None

        if not self._queue_url:
            raise QueueError("SQS queue URL not configured")

    def _get_client(self):
        """Lazily create SQS client with proper timeouts."""
        if self._client is None:
            try:
                import boto3
                from botocore.config import Config

                settings = get_settings()
                session_kwargs = {}
                if settings.aws_access_key_id:
                    session_kwargs["aws_access_key_id"] = settings.aws_access_key_id
                if settings.aws_secret_access_key:
                    session_kwargs["aws_secret_access_key"] = settings.aws_secret_access_key

                # Configure timeouts to prevent operations from hanging indefinitely
                # read_timeout should be > WaitTimeSeconds for long polling to work properly
                boto_config = Config(
                    connect_timeout=DEFAULT_CONNECT_TIMEOUT,
                    read_timeout=DEFAULT_READ_TIMEOUT,
                    retries={
                        "max_attempts": 3,
                        "mode": "adaptive",  # Uses exponential backoff with jitter
                    },
                )

                client_kwargs = {
                    "region_name": self._region,
                    "config": boto_config,
                }
                if self._endpoint_url:
                    client_kwargs["endpoint_url"] = self._endpoint_url

                session = boto3.Session(**session_kwargs)
                self._client = session.client("sqs", **client_kwargs)
            except ImportError:
                raise QueueError("boto3 is required for SQS. Install with: pip install boto3")

        return self._client

    async def send_message(
        self,
        message_body: dict[str, Any],
        delay_seconds: int = 0,
    ) -> str:
        """Send a message to SQS."""
        try:
            import asyncio

            client = self._get_client()
            loop = asyncio.get_event_loop()

            response = await loop.run_in_executor(
                None,
                lambda: client.send_message(
                    QueueUrl=self._queue_url,
                    MessageBody=json.dumps(message_body),
                    DelaySeconds=delay_seconds,
                ),
            )

            message_id = response["MessageId"]
            logger.info(
                "Message sent to SQS",
                extra={
                    "message_id": message_id,
                    "queue_url": self._queue_url,
                    "delay_seconds": delay_seconds,
                },
            )
            return message_id

        except Exception as e:
            logger.error(
                "Failed to send message to SQS",
                extra={"error": str(e), "queue_url": self._queue_url},
            )
            raise QueueError(f"Failed to send message: {e}")

    async def receive_messages(
        self,
        max_messages: int = 1,
        wait_time_seconds: int = 20,
    ) -> list[QueueMessage]:
        """Receive messages from SQS with long polling."""
        try:
            import asyncio

            client = self._get_client()
            loop = asyncio.get_event_loop()

            response = await loop.run_in_executor(
                None,
                lambda: client.receive_message(
                    QueueUrl=self._queue_url,
                    MaxNumberOfMessages=min(max_messages, 10),  # SQS max is 10
                    WaitTimeSeconds=wait_time_seconds,
                    AttributeNames=["All"],
                    MessageAttributeNames=["All"],
                ),
            )

            messages = []
            for msg in response.get("Messages", []):
                try:
                    body = json.loads(msg["Body"])
                except json.JSONDecodeError:
                    body = {"raw": msg["Body"]}

                messages.append(
                    QueueMessage(
                        message_id=msg["MessageId"],
                        receipt_handle=msg["ReceiptHandle"],
                        body=body,
                        attributes=msg.get("Attributes", {}),
                    )
                )

            if messages:
                logger.debug(
                    "Messages received from SQS",
                    extra={"count": len(messages), "queue_url": self._queue_url},
                )

            return messages

        except Exception as e:
            logger.error(
                "Failed to receive messages from SQS",
                extra={"error": str(e), "queue_url": self._queue_url},
            )
            raise QueueError(f"Failed to receive messages: {e}")

    async def delete_message(self, receipt_handle: str) -> None:
        """Delete a message from SQS."""
        try:
            import asyncio

            client = self._get_client()
            loop = asyncio.get_event_loop()

            await loop.run_in_executor(
                None,
                lambda: client.delete_message(
                    QueueUrl=self._queue_url,
                    ReceiptHandle=receipt_handle,
                ),
            )

            logger.debug(
                "Message deleted from SQS",
                extra={"receipt_handle": receipt_handle[:50], "queue_url": self._queue_url},
            )

        except Exception as e:
            logger.error(
                "Failed to delete message from SQS",
                extra={"error": str(e), "queue_url": self._queue_url},
            )
            raise QueueError(f"Failed to delete message: {e}")

    async def change_visibility(
        self,
        receipt_handle: str,
        visibility_timeout: int,
    ) -> None:
        """Change message visibility timeout."""
        try:
            import asyncio

            client = self._get_client()
            loop = asyncio.get_event_loop()

            await loop.run_in_executor(
                None,
                lambda: client.change_message_visibility(
                    QueueUrl=self._queue_url,
                    ReceiptHandle=receipt_handle,
                    VisibilityTimeout=visibility_timeout,
                ),
            )

            logger.debug(
                "Message visibility changed",
                extra={
                    "receipt_handle": receipt_handle[:50],
                    "visibility_timeout": visibility_timeout,
                    "queue_url": self._queue_url,
                },
            )

        except Exception as e:
            logger.error(
                "Failed to change message visibility",
                extra={"error": str(e), "queue_url": self._queue_url},
            )
            raise QueueError(f"Failed to change visibility: {e}")

    def _get_dlq_url(self) -> str:
        """Get the DLQ URL by convention (main queue URL + '-dlq')."""
        # SQS queue URLs end with queue name, e.g., .../000000000000/my-queue
        # DLQ convention: my-queue-dlq
        return self._queue_url + "-dlq"

    async def send_to_dlq(
        self,
        message: QueueMessage,
        error: str,
    ) -> str:
        """Send a failed message to the dead letter queue."""
        try:
            import asyncio

            client = self._get_client()
            loop = asyncio.get_event_loop()
            dlq_url = self._get_dlq_url()

            # Include original message attributes and error info
            message_body = {
                **message.body,
                "_dlq_metadata": {
                    "original_message_id": message.message_id,
                    "error": error,
                    "original_attributes": message.attributes,
                },
            }

            response = await loop.run_in_executor(
                None,
                lambda: client.send_message(
                    QueueUrl=dlq_url,
                    MessageBody=json.dumps(message_body),
                ),
            )

            message_id = response["MessageId"]
            logger.warning(
                "Message sent to DLQ",
                extra={
                    "message_id": message.message_id,
                    "dlq_message_id": message_id,
                    "error": error,
                    "dlq_url": dlq_url,
                },
            )
            return message_id

        except Exception as e:
            logger.error(
                "Failed to send message to DLQ",
                extra={"error": str(e), "dlq_url": self._get_dlq_url()},
            )
            raise QueueError(f"Failed to send to DLQ: {e}")

    async def get_dlq_messages(
        self,
        max_messages: int = 10,
    ) -> list[QueueMessage]:
        """Get messages from the dead letter queue for inspection."""
        try:
            import asyncio

            client = self._get_client()
            loop = asyncio.get_event_loop()
            dlq_url = self._get_dlq_url()

            response = await loop.run_in_executor(
                None,
                lambda: client.receive_message(
                    QueueUrl=dlq_url,
                    MaxNumberOfMessages=min(max_messages, 10),
                    WaitTimeSeconds=1,  # Short poll for inspection
                    AttributeNames=["All"],
                    MessageAttributeNames=["All"],
                ),
            )

            messages = []
            for msg in response.get("Messages", []):
                try:
                    body = json.loads(msg["Body"])
                except json.JSONDecodeError:
                    body = {"raw": msg["Body"]}

                messages.append(
                    QueueMessage(
                        message_id=msg["MessageId"],
                        receipt_handle=msg["ReceiptHandle"],
                        body=body,
                        attributes=msg.get("Attributes", {}),
                    )
                )

            logger.debug(
                "Messages retrieved from DLQ",
                extra={"count": len(messages), "dlq_url": dlq_url},
            )
            return messages

        except Exception as e:
            logger.error(
                "Failed to get messages from DLQ",
                extra={"error": str(e), "dlq_url": self._get_dlq_url()},
            )
            raise QueueError(f"Failed to get DLQ messages: {e}")
