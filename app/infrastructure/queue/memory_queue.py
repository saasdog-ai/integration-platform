"""In-memory message queue for local development and testing."""

import asyncio
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.logging import get_logger
from app.domain.entities import QueueMessage
from app.domain.interfaces import MessageQueueInterface

logger = get_logger(__name__)


@dataclass
class InternalMessage:
    """Internal message representation."""

    message_id: str
    body: dict[str, Any]
    receipt_handle: str
    sent_at: datetime
    visible_at: datetime
    receive_count: int = 0
    attributes: dict[str, Any] = field(default_factory=dict)


class InMemoryQueue(MessageQueueInterface):
    """
    In-memory message queue for local development and testing.

    This implementation is NOT suitable for production use.
    It does not persist messages across restarts.
    """

    def __init__(
        self,
        visibility_timeout: int = 30,
        max_receive_count: int = 3,
    ) -> None:
        """
        Initialize the in-memory queue.

        Args:
            visibility_timeout: Default visibility timeout in seconds.
            max_receive_count: Max times a message can be received before going to DLQ.
        """
        self._messages: deque[InternalMessage] = deque()
        self._in_flight: dict[str, InternalMessage] = {}
        self._dlq: deque[InternalMessage] = deque()  # Dead letter queue
        self._visibility_timeout = visibility_timeout
        self._max_receive_count = max_receive_count
        self._lock = asyncio.Lock()

    async def send_message(
        self,
        message_body: dict[str, Any],
        delay_seconds: int = 0,
    ) -> str:
        """Send a message to the queue."""
        async with self._lock:
            message_id = str(uuid.uuid4())
            now = datetime.now(UTC)
            visible_at = now + timedelta(seconds=delay_seconds)

            message = InternalMessage(
                message_id=message_id,
                body=message_body,
                receipt_handle=str(uuid.uuid4()),
                sent_at=now,
                visible_at=visible_at,
                attributes={
                    "SentTimestamp": str(int(now.timestamp() * 1000)),
                    "ApproximateReceiveCount": "0",
                },
            )
            self._messages.append(message)
            logger.debug(
                "Message sent to in-memory queue",
                extra={"message_id": message_id, "delay_seconds": delay_seconds},
            )
            return message_id

    async def receive_messages(
        self,
        max_messages: int = 1,
        wait_time_seconds: int = 20,
    ) -> list[QueueMessage]:
        """Receive messages from the queue with long polling simulation."""
        end_time = datetime.now(UTC) + timedelta(seconds=wait_time_seconds)
        received: list[QueueMessage] = []

        while datetime.now(UTC) < end_time and len(received) < max_messages:
            async with self._lock:
                now = datetime.now(UTC)
                messages_to_deliver: list[InternalMessage] = []

                # Find visible messages
                remaining: deque[InternalMessage] = deque()
                for msg in self._messages:
                    if msg.visible_at <= now and len(messages_to_deliver) < (
                        max_messages - len(received)
                    ):
                        messages_to_deliver.append(msg)
                    else:
                        remaining.append(msg)
                self._messages = remaining

                # Process messages
                for msg in messages_to_deliver:
                    msg.receive_count += 1
                    msg.receipt_handle = str(uuid.uuid4())
                    msg.visible_at = now + timedelta(seconds=self._visibility_timeout)
                    msg.attributes["ApproximateReceiveCount"] = str(msg.receive_count)

                    # Check if message exceeded max receive count - move to DLQ
                    if msg.receive_count > self._max_receive_count:
                        msg.attributes["DLQReason"] = (
                            f"MaxReceiveCount ({self._max_receive_count}) exceeded"
                        )
                        msg.attributes["MovedToDLQAt"] = str(int(now.timestamp() * 1000))
                        self._dlq.append(msg)
                        logger.warning(
                            "Message moved to DLQ after exceeding max receive count",
                            extra={
                                "message_id": msg.message_id,
                                "receive_count": msg.receive_count,
                                "max_receive_count": self._max_receive_count,
                            },
                        )
                        continue

                    self._in_flight[msg.receipt_handle] = msg
                    received.append(
                        QueueMessage(
                            message_id=msg.message_id,
                            receipt_handle=msg.receipt_handle,
                            body=msg.body,
                            attributes=msg.attributes,
                        )
                    )

            if received:
                break

            # Wait a bit before checking again (simulate long polling)
            await asyncio.sleep(0.1)

        if received:
            logger.debug(
                "Messages received from in-memory queue",
                extra={"count": len(received)},
            )

        return received

    async def delete_message(self, receipt_handle: str) -> None:
        """Delete a message from the queue."""
        async with self._lock:
            if receipt_handle in self._in_flight:
                del self._in_flight[receipt_handle]
                logger.debug(
                    "Message deleted from in-memory queue",
                    extra={"receipt_handle": receipt_handle},
                )
            else:
                logger.warning(
                    "Message not found for deletion",
                    extra={"receipt_handle": receipt_handle},
                )

    async def change_visibility(
        self,
        receipt_handle: str,
        visibility_timeout: int,
    ) -> None:
        """Extend message visibility timeout."""
        async with self._lock:
            if receipt_handle in self._in_flight:
                msg = self._in_flight[receipt_handle]
                msg.visible_at = datetime.now(UTC) + timedelta(seconds=visibility_timeout)
                logger.debug(
                    "Message visibility changed",
                    extra={
                        "receipt_handle": receipt_handle,
                        "visibility_timeout": visibility_timeout,
                    },
                )
            else:
                logger.warning(
                    "Message not found for visibility change",
                    extra={"receipt_handle": receipt_handle},
                )

    async def return_in_flight_messages(self) -> None:
        """Return all in-flight messages to the queue (for testing)."""
        async with self._lock:
            now = datetime.now(UTC)
            for msg in self._in_flight.values():
                msg.visible_at = now
                self._messages.append(msg)
            self._in_flight.clear()

    async def purge(self) -> None:
        """Purge all messages from the queue (for testing)."""
        async with self._lock:
            self._messages.clear()
            self._in_flight.clear()
            logger.info("In-memory queue purged")

    @property
    def message_count(self) -> int:
        """Get approximate message count (for testing)."""
        return len(self._messages)

    @property
    def in_flight_count(self) -> int:
        """Get in-flight message count (for testing)."""
        return len(self._in_flight)

    @property
    def dlq_count(self) -> int:
        """Get dead letter queue message count (for testing)."""
        return len(self._dlq)

    async def send_to_dlq(
        self,
        message: QueueMessage,
        error: str,
    ) -> str:
        """Send a failed message to the dead letter queue."""
        async with self._lock:
            now = datetime.now(UTC)

            # Remove from in-flight if present
            if message.receipt_handle in self._in_flight:
                del self._in_flight[message.receipt_handle]

            dlq_message = InternalMessage(
                message_id=message.message_id,
                body=message.body,
                receipt_handle=str(uuid.uuid4()),
                sent_at=now,
                visible_at=now,
                receive_count=int(message.attributes.get("ApproximateReceiveCount", 1)),
                attributes={
                    **message.attributes,
                    "DLQReason": error,
                    "MovedToDLQAt": str(int(now.timestamp() * 1000)),
                },
            )
            self._dlq.append(dlq_message)

            logger.warning(
                "Message sent to DLQ",
                extra={
                    "message_id": message.message_id,
                    "error": error,
                },
            )
            return dlq_message.message_id

    async def get_dlq_messages(
        self,
        max_messages: int = 10,
    ) -> list[QueueMessage]:
        """Get messages from the dead letter queue for inspection."""
        async with self._lock:
            messages: list[QueueMessage] = []
            for i, msg in enumerate(self._dlq):
                if i >= max_messages:
                    break
                messages.append(
                    QueueMessage(
                        message_id=msg.message_id,
                        receipt_handle=msg.receipt_handle,
                        body=msg.body,
                        attributes=msg.attributes,
                    )
                )
            return messages

    async def purge_dlq(self) -> int:
        """Purge all messages from the DLQ (for testing). Returns count of purged messages."""
        async with self._lock:
            count = len(self._dlq)
            self._dlq.clear()
            logger.info("Dead letter queue purged", extra={"count": count})
            return count
