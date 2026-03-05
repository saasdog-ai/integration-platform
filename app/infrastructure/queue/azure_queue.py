"""Azure Queue Storage message queue implementation."""

import json
from typing import Any

from app.core.config import get_settings
from app.core.exceptions import QueueError
from app.core.logging import get_logger
from app.domain.entities import QueueMessage
from app.domain.interfaces import MessageQueueInterface

logger = get_logger(__name__)


class AzureQueue(MessageQueueInterface):
    """Azure Queue Storage message queue implementation."""

    def __init__(
        self,
        queue_name: str | None = None,
        account_name: str | None = None,
    ) -> None:
        """
        Initialize Azure Queue Storage.

        Args:
            queue_name: Queue name. If not provided, derives from settings.queue_url.
            account_name: Azure storage account name.
        """
        settings = get_settings()
        self._queue_name = queue_name or self._derive_queue_name(settings.queue_url)
        self._account_name = account_name
        self._queue_client = None

        if not self._queue_name:
            raise QueueError("Azure queue name not configured")

    @staticmethod
    def _derive_queue_name(queue_url: str | None) -> str | None:
        """Derive queue name from queue_url setting (reuse the config field)."""
        return queue_url

    def _get_queue_client(self):
        """Lazily create Azure Queue client."""
        if self._queue_client is None:
            try:
                import os

                from azure.storage.queue import QueueClient

                connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
                if connection_string:
                    self._queue_client = QueueClient.from_connection_string(
                        connection_string, queue_name=self._queue_name
                    )
                else:
                    from azure.identity import DefaultAzureCredential

                    account_name = self._account_name or os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
                    if not account_name:
                        raise QueueError(
                            "Azure storage account name not configured. "
                            "Set AZURE_STORAGE_ACCOUNT_NAME or AZURE_STORAGE_CONNECTION_STRING."
                        )
                    account_url = f"https://{account_name}.queue.core.windows.net"
                    credential = DefaultAzureCredential()
                    self._queue_client = QueueClient(
                        account_url=account_url,
                        queue_name=self._queue_name,
                        credential=credential,
                    )

                # Ensure queue exists
                try:
                    self._queue_client.get_queue_properties()
                except Exception:
                    self._queue_client.create_queue()
                    logger.info(f"Created Azure queue: {self._queue_name}")

            except ImportError:
                raise QueueError(
                    "azure-storage-queue and azure-identity are required. "
                    "Install with: pip install azure-storage-queue azure-identity"
                ) from None

        return self._queue_client

    async def send_message(
        self,
        message_body: dict[str, Any],
        delay_seconds: int = 0,
    ) -> str:
        """Send a message to Azure Queue."""
        try:
            import asyncio

            client = self._get_queue_client()

            kwargs: dict[str, Any] = {}
            if delay_seconds > 0:
                kwargs["visibility_timeout"] = delay_seconds

            response = await asyncio.to_thread(
                client.send_message,
                json.dumps(message_body),
                **kwargs,
            )

            message_id = str(response.id)
            logger.info(
                "Message sent to Azure Queue",
                extra={
                    "message_id": message_id,
                    "queue_name": self._queue_name,
                    "delay_seconds": delay_seconds,
                },
            )
            return message_id

        except Exception as e:
            logger.error(
                "Failed to send message to Azure Queue",
                extra={"error": str(e), "queue_name": self._queue_name},
            )
            raise QueueError(f"Failed to send message: {e}") from e

    async def receive_messages(
        self,
        max_messages: int = 1,
        wait_time_seconds: int = 20,
    ) -> list[QueueMessage]:
        """Receive messages from Azure Queue."""
        try:
            import asyncio

            client = self._get_queue_client()

            # Azure Queue Storage doesn't support long polling like SQS.
            # We receive what's available now with a 60s visibility timeout.
            raw_messages = await asyncio.to_thread(
                client.receive_messages,
                messages_per_page=min(max_messages, 32),  # Azure max is 32
                visibility_timeout=60,
            )

            messages = []
            for msg in raw_messages:
                try:
                    body = json.loads(msg.content)
                except json.JSONDecodeError:
                    body = {"raw": msg.content}

                # Encode both message_id and pop_receipt into receipt_handle
                # so we can delete/update the message later.
                receipt_handle = f"{msg.id}:{msg.pop_receipt}"

                messages.append(
                    QueueMessage(
                        message_id=str(msg.id),
                        receipt_handle=receipt_handle,
                        body=body,
                        attributes={
                            "ApproximateReceiveCount": str(msg.dequeue_count or 1),
                            "SentTimestamp": str(int(msg.inserted_on.timestamp() * 1000))
                            if msg.inserted_on
                            else "0",
                        },
                    )
                )

            if messages:
                logger.debug(
                    "Messages received from Azure Queue",
                    extra={"count": len(messages), "queue_name": self._queue_name},
                )

            return messages

        except Exception as e:
            logger.error(
                "Failed to receive messages from Azure Queue",
                extra={"error": str(e), "queue_name": self._queue_name},
            )
            raise QueueError(f"Failed to receive messages: {e}") from e

    def _parse_receipt_handle(self, receipt_handle: str) -> tuple[str, str]:
        """Parse receipt_handle into (message_id, pop_receipt)."""
        if ":" not in receipt_handle:
            raise QueueError(f"Invalid Azure receipt handle format: {receipt_handle}")
        message_id, pop_receipt = receipt_handle.split(":", 1)
        return message_id, pop_receipt

    async def delete_message(self, receipt_handle: str) -> None:
        """Delete a message from Azure Queue."""
        try:
            import asyncio

            client = self._get_queue_client()
            message_id, pop_receipt = self._parse_receipt_handle(receipt_handle)

            await asyncio.to_thread(client.delete_message, message_id, pop_receipt)

            logger.debug(
                "Message deleted from Azure Queue",
                extra={"message_id": message_id, "queue_name": self._queue_name},
            )

        except Exception as e:
            logger.error(
                "Failed to delete message from Azure Queue",
                extra={"error": str(e), "queue_name": self._queue_name},
            )
            raise QueueError(f"Failed to delete message: {e}") from e

    async def change_visibility(
        self,
        receipt_handle: str,
        visibility_timeout: int,
    ) -> None:
        """Extend message visibility timeout."""
        try:
            import asyncio

            client = self._get_queue_client()
            message_id, pop_receipt = self._parse_receipt_handle(receipt_handle)

            await asyncio.to_thread(
                client.update_message,
                message_id,
                pop_receipt,
                visibility_timeout=visibility_timeout,
            )

            logger.debug(
                "Message visibility changed in Azure Queue",
                extra={
                    "message_id": message_id,
                    "visibility_timeout": visibility_timeout,
                    "queue_name": self._queue_name,
                },
            )

        except Exception as e:
            logger.error(
                "Failed to change message visibility in Azure Queue",
                extra={"error": str(e), "queue_name": self._queue_name},
            )
            raise QueueError(f"Failed to change visibility: {e}") from e

    async def send_to_dlq(
        self,
        message: QueueMessage,
        error: str,
    ) -> str:
        """Send a failed message to the dead letter queue."""
        try:
            import asyncio

            # DLQ convention: main queue name + "-dlq"
            dlq_name = f"{self._queue_name}-dlq"

            import os

            from azure.storage.queue import QueueClient

            connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
            if connection_string:
                dlq_client = QueueClient.from_connection_string(
                    connection_string, queue_name=dlq_name
                )
            else:
                from azure.identity import DefaultAzureCredential

                account_name = self._account_name or os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
                account_url = f"https://{account_name}.queue.core.windows.net"
                credential = DefaultAzureCredential()
                dlq_client = QueueClient(
                    account_url=account_url,
                    queue_name=dlq_name,
                    credential=credential,
                )

            # Ensure DLQ exists
            try:
                dlq_client.get_queue_properties()
            except Exception:
                dlq_client.create_queue()
                logger.info(f"Created Azure DLQ: {dlq_name}")

            message_body = {
                **message.body,
                "_dlq_metadata": {
                    "original_message_id": message.message_id,
                    "error": error,
                    "original_attributes": message.attributes,
                },
            }

            response = await asyncio.to_thread(dlq_client.send_message, json.dumps(message_body))

            dlq_message_id = str(response.id)
            logger.warning(
                "Message sent to Azure DLQ",
                extra={
                    "message_id": message.message_id,
                    "dlq_message_id": dlq_message_id,
                    "error": error,
                    "dlq_name": dlq_name,
                },
            )
            return dlq_message_id

        except Exception as e:
            logger.error(
                "Failed to send message to Azure DLQ",
                extra={"error": str(e)},
            )
            raise QueueError(f"Failed to send to DLQ: {e}") from e

    async def get_dlq_messages(
        self,
        max_messages: int = 10,
    ) -> list[QueueMessage]:
        """Get messages from the dead letter queue for inspection."""
        try:
            import asyncio

            dlq_name = f"{self._queue_name}-dlq"

            import os

            from azure.storage.queue import QueueClient

            connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
            if connection_string:
                dlq_client = QueueClient.from_connection_string(
                    connection_string, queue_name=dlq_name
                )
            else:
                from azure.identity import DefaultAzureCredential

                account_name = self._account_name or os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
                account_url = f"https://{account_name}.queue.core.windows.net"
                credential = DefaultAzureCredential()
                dlq_client = QueueClient(
                    account_url=account_url,
                    queue_name=dlq_name,
                    credential=credential,
                )

            raw_messages = await asyncio.to_thread(
                dlq_client.receive_messages,
                messages_per_page=min(max_messages, 32),
                visibility_timeout=30,
            )

            messages = []
            for msg in raw_messages:
                try:
                    body = json.loads(msg.content)
                except json.JSONDecodeError:
                    body = {"raw": msg.content}

                messages.append(
                    QueueMessage(
                        message_id=str(msg.id),
                        receipt_handle=f"{msg.id}:{msg.pop_receipt}",
                        body=body,
                        attributes={},
                    )
                )

            logger.debug(
                "Messages retrieved from Azure DLQ",
                extra={"count": len(messages), "dlq_name": dlq_name},
            )
            return messages

        except Exception as e:
            logger.error(
                "Failed to get messages from Azure DLQ",
                extra={"error": str(e)},
            )
            raise QueueError(f"Failed to get DLQ messages: {e}") from e
