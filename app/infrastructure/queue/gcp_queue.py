"""Google Cloud Pub/Sub message queue implementation."""

import json
from typing import Any

from app.core.config import get_settings
from app.core.exceptions import QueueError
from app.core.logging import get_logger
from app.domain.entities import QueueMessage
from app.domain.interfaces import MessageQueueInterface

logger = get_logger(__name__)


class GCPPubSubQueue(MessageQueueInterface):
    """Google Cloud Pub/Sub message queue implementation."""

    def __init__(
        self,
        topic_name: str | None = None,
        subscription_name: str | None = None,
        project_id: str | None = None,
    ) -> None:
        """
        Initialize GCP Pub/Sub queue.

        Args:
            topic_name: Pub/Sub topic name. If not provided, derives from settings.queue_url.
            subscription_name: Subscription name. Defaults to "{topic_name}-sub".
            project_id: GCP project ID. If not provided, uses settings or ADC.
        """
        settings = get_settings()
        self._topic_name = topic_name or settings.queue_url
        self._subscription_name = subscription_name or f"{self._topic_name}-sub"
        self._project_id = project_id or settings.gcp_project_id
        self._publisher = None
        self._subscriber = None
        self._topic_path: str | None = None
        self._subscription_path: str | None = None
        self._dlq_topic_path: str | None = None
        self._dlq_subscription_path: str | None = None

        if not self._topic_name:
            raise QueueError("GCP Pub/Sub topic name not configured")

    def _ensure_clients(self):
        """Lazily create Pub/Sub clients and ensure topic/subscription exist."""
        if self._publisher is not None:
            return

        try:
            from google.api_core.exceptions import NotFound
            from google.cloud import pubsub_v1
        except ImportError:
            raise QueueError(
                "google-cloud-pubsub is required. Install with: pip install google-cloud-pubsub"
            ) from None

        self._publisher = pubsub_v1.PublisherClient()
        self._subscriber = pubsub_v1.SubscriberClient()

        # Resolve project ID from ADC if not provided
        if not self._project_id:
            import google.auth

            _, self._project_id = google.auth.default()
            if not self._project_id:
                raise QueueError(
                    "GCP project ID not configured. Set GCP_PROJECT_ID or configure ADC."
                )

        self._topic_path = self._publisher.topic_path(self._project_id, self._topic_name)
        self._subscription_path = self._subscriber.subscription_path(
            self._project_id, self._subscription_name
        )

        # Ensure topic exists
        try:
            self._publisher.get_topic(topic=self._topic_path)
        except NotFound:
            self._publisher.create_topic(name=self._topic_path)
            logger.info(f"Created Pub/Sub topic: {self._topic_name}")

        # Ensure subscription exists
        try:
            self._subscriber.get_subscription(subscription=self._subscription_path)
        except NotFound:
            self._subscriber.create_subscription(
                name=self._subscription_path,
                topic=self._topic_path,
                ack_deadline_seconds=60,
            )
            logger.info(f"Created Pub/Sub subscription: {self._subscription_name}")

    def _ensure_dlq(self):
        """Ensure DLQ topic and subscription exist."""
        if self._dlq_topic_path is not None:
            return

        from google.api_core.exceptions import NotFound

        dlq_topic_name = f"{self._topic_name}-dlq"
        dlq_sub_name = f"{self._subscription_name}-dlq"

        self._dlq_topic_path = self._publisher.topic_path(self._project_id, dlq_topic_name)
        self._dlq_subscription_path = self._subscriber.subscription_path(
            self._project_id, dlq_sub_name
        )

        try:
            self._publisher.get_topic(topic=self._dlq_topic_path)
        except NotFound:
            self._publisher.create_topic(name=self._dlq_topic_path)
            logger.info(f"Created Pub/Sub DLQ topic: {dlq_topic_name}")

        try:
            self._subscriber.get_subscription(subscription=self._dlq_subscription_path)
        except NotFound:
            self._subscriber.create_subscription(
                name=self._dlq_subscription_path,
                topic=self._dlq_topic_path,
                ack_deadline_seconds=60,
            )
            logger.info(f"Created Pub/Sub DLQ subscription: {dlq_sub_name}")

    async def send_message(
        self,
        message_body: dict[str, Any],
        delay_seconds: int = 0,
    ) -> str:
        """Send a message to Pub/Sub."""
        try:
            import asyncio

            self._ensure_clients()

            message_data = json.dumps(message_body).encode("utf-8")

            # Pub/Sub doesn't natively support delay_seconds.
            # We publish immediately; delay would need a Cloud Scheduler or attribute-based approach.
            future = await asyncio.to_thread(
                self._publisher.publish,
                self._topic_path,
                message_data,
            )
            message_id = await asyncio.to_thread(future.result)

            logger.info(
                "Message sent to Pub/Sub",
                extra={
                    "message_id": message_id,
                    "topic": self._topic_name,
                    "delay_seconds": delay_seconds,
                },
            )
            return str(message_id)

        except Exception as e:
            logger.error(
                "Failed to send message to Pub/Sub",
                extra={"error": str(e), "topic": self._topic_name},
            )
            raise QueueError(f"Failed to send message: {e}") from e

    async def receive_messages(
        self,
        max_messages: int = 1,
        wait_time_seconds: int = 20,
    ) -> list[QueueMessage]:
        """Receive messages from Pub/Sub using synchronous pull."""
        try:
            import asyncio

            self._ensure_clients()

            response = await asyncio.to_thread(
                self._subscriber.pull,
                subscription=self._subscription_path,
                max_messages=min(max_messages, 100),  # Pub/Sub max is 1000, keep reasonable
                timeout=wait_time_seconds,
            )

            messages = []
            for received_msg in response.received_messages:
                try:
                    body = json.loads(received_msg.message.data.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    body = {"raw": received_msg.message.data.decode("utf-8", errors="replace")}

                messages.append(
                    QueueMessage(
                        message_id=received_msg.message.message_id,
                        receipt_handle=received_msg.ack_id,
                        body=body,
                        attributes={
                            "ApproximateReceiveCount": str(received_msg.delivery_attempt or 1),
                            "SentTimestamp": str(
                                int(received_msg.message.publish_time.timestamp() * 1000)
                            )
                            if received_msg.message.publish_time
                            else "0",
                        },
                    )
                )

            if messages:
                logger.debug(
                    "Messages received from Pub/Sub",
                    extra={"count": len(messages), "subscription": self._subscription_name},
                )

            return messages

        except Exception as e:
            # Pub/Sub raises DeadlineExceeded on timeout with no messages — that's normal
            error_type = type(e).__name__
            if error_type == "DeadlineExceeded":
                return []
            logger.error(
                "Failed to receive messages from Pub/Sub",
                extra={"error": str(e), "subscription": self._subscription_name},
            )
            raise QueueError(f"Failed to receive messages: {e}") from e

    async def delete_message(self, receipt_handle: str) -> None:
        """Acknowledge (delete) a message from Pub/Sub."""
        try:
            import asyncio

            self._ensure_clients()

            await asyncio.to_thread(
                self._subscriber.acknowledge,
                subscription=self._subscription_path,
                ack_ids=[receipt_handle],
            )

            logger.debug(
                "Message acknowledged in Pub/Sub",
                extra={"subscription": self._subscription_name},
            )

        except Exception as e:
            logger.error(
                "Failed to acknowledge message in Pub/Sub",
                extra={"error": str(e), "subscription": self._subscription_name},
            )
            raise QueueError(f"Failed to delete message: {e}") from e

    async def change_visibility(
        self,
        receipt_handle: str,
        visibility_timeout: int,
    ) -> None:
        """Extend message ack deadline (visibility timeout equivalent)."""
        try:
            import asyncio

            self._ensure_clients()

            await asyncio.to_thread(
                self._subscriber.modify_ack_deadline,
                subscription=self._subscription_path,
                ack_ids=[receipt_handle],
                ack_deadline_seconds=visibility_timeout,
            )

            logger.debug(
                "Message ack deadline extended in Pub/Sub",
                extra={
                    "visibility_timeout": visibility_timeout,
                    "subscription": self._subscription_name,
                },
            )

        except Exception as e:
            logger.error(
                "Failed to extend message ack deadline in Pub/Sub",
                extra={"error": str(e), "subscription": self._subscription_name},
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

            self._ensure_clients()
            self._ensure_dlq()

            message_body = {
                **message.body,
                "_dlq_metadata": {
                    "original_message_id": message.message_id,
                    "error": error,
                    "original_attributes": message.attributes,
                },
            }

            message_data = json.dumps(message_body).encode("utf-8")
            future = await asyncio.to_thread(
                self._publisher.publish,
                self._dlq_topic_path,
                message_data,
            )
            dlq_message_id = await asyncio.to_thread(future.result)

            logger.warning(
                "Message sent to Pub/Sub DLQ",
                extra={
                    "message_id": message.message_id,
                    "dlq_message_id": dlq_message_id,
                    "error": error,
                },
            )
            return str(dlq_message_id)

        except Exception as e:
            logger.error(
                "Failed to send message to Pub/Sub DLQ",
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

            self._ensure_clients()
            self._ensure_dlq()

            response = await asyncio.to_thread(
                self._subscriber.pull,
                subscription=self._dlq_subscription_path,
                max_messages=min(max_messages, 100),
                timeout=5,  # Short poll for inspection
            )

            messages = []
            for received_msg in response.received_messages:
                try:
                    body = json.loads(received_msg.message.data.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    body = {"raw": received_msg.message.data.decode("utf-8", errors="replace")}

                messages.append(
                    QueueMessage(
                        message_id=received_msg.message.message_id,
                        receipt_handle=received_msg.ack_id,
                        body=body,
                        attributes={},
                    )
                )

            logger.debug(
                "Messages retrieved from Pub/Sub DLQ",
                extra={"count": len(messages)},
            )
            return messages

        except Exception as e:
            error_type = type(e).__name__
            if error_type == "DeadlineExceeded":
                return []
            logger.error(
                "Failed to get messages from Pub/Sub DLQ",
                extra={"error": str(e)},
            )
            raise QueueError(f"Failed to get DLQ messages: {e}") from e
