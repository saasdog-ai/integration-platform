"""Unit tests for queue infrastructure."""

import pytest

from app.infrastructure.queue.memory_queue import InMemoryQueue


class TestInMemoryQueue:
    """Tests for InMemoryQueue."""

    @pytest.fixture
    def queue(self) -> InMemoryQueue:
        """Create a fresh in-memory queue."""
        return InMemoryQueue(visibility_timeout=5)

    @pytest.mark.asyncio
    async def test_send_message(self, queue: InMemoryQueue):
        """Test sending a message."""
        message_id = await queue.send_message({"test": "data"})
        assert message_id is not None
        assert queue.message_count == 1

    @pytest.mark.asyncio
    async def test_receive_message(self, queue: InMemoryQueue):
        """Test receiving a message."""
        await queue.send_message({"test": "data"})

        messages = await queue.receive_messages(max_messages=1, wait_time_seconds=1)
        assert len(messages) == 1
        assert messages[0].body == {"test": "data"}
        assert queue.in_flight_count == 1

    @pytest.mark.asyncio
    async def test_delete_message(self, queue: InMemoryQueue):
        """Test deleting a message."""
        await queue.send_message({"test": "data"})

        messages = await queue.receive_messages(max_messages=1, wait_time_seconds=1)
        receipt_handle = messages[0].receipt_handle

        await queue.delete_message(receipt_handle)
        assert queue.in_flight_count == 0

    @pytest.mark.asyncio
    async def test_change_visibility(self, queue: InMemoryQueue):
        """Test changing message visibility."""
        await queue.send_message({"test": "data"})

        messages = await queue.receive_messages(max_messages=1, wait_time_seconds=1)
        receipt_handle = messages[0].receipt_handle

        # Should not raise
        await queue.change_visibility(receipt_handle, 60)

    @pytest.mark.asyncio
    async def test_receive_multiple_messages(self, queue: InMemoryQueue):
        """Test receiving multiple messages."""
        for i in range(5):
            await queue.send_message({"index": i})

        messages = await queue.receive_messages(max_messages=3, wait_time_seconds=1)
        assert len(messages) == 3
        assert queue.in_flight_count == 3
        assert queue.message_count == 2  # 2 remaining

    @pytest.mark.asyncio
    async def test_delayed_message(self, queue: InMemoryQueue):
        """Test message with delay."""
        await queue.send_message({"test": "delayed"}, delay_seconds=100)

        # Should not receive the delayed message immediately
        messages = await queue.receive_messages(max_messages=1, wait_time_seconds=0)
        assert len(messages) == 0

    @pytest.mark.asyncio
    async def test_purge(self, queue: InMemoryQueue):
        """Test purging all messages."""
        for i in range(5):
            await queue.send_message({"index": i})

        await queue.purge()
        assert queue.message_count == 0
        assert queue.in_flight_count == 0

    @pytest.mark.asyncio
    async def test_return_in_flight_messages(self, queue: InMemoryQueue):
        """Test returning in-flight messages to queue."""
        await queue.send_message({"test": "data"})

        # Receive to make in-flight
        await queue.receive_messages(max_messages=1, wait_time_seconds=1)
        assert queue.in_flight_count == 1
        assert queue.message_count == 0

        # Return to queue
        await queue.return_in_flight_messages()
        assert queue.in_flight_count == 0
        assert queue.message_count == 1
