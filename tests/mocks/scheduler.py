"""Mock scheduler for testing."""

from uuid import UUID

from app.domain.interfaces import SyncSchedulerInterface


class MockSyncScheduler(SyncSchedulerInterface):
    """In-memory mock scheduler for testing.

    Tracks scheduler state and method calls for verification in tests.
    """

    def __init__(self) -> None:
        self.started = False
        self.stopped = False
        self.refresh_count = 0
        self.scheduled_jobs: list[tuple[UUID, UUID, str]] = []  # (client_id, integration_id, cron)
        self.trigger_sync_calls: list[tuple[UUID, UUID]] = []  # (client_id, integration_id)

    async def start(self) -> None:
        """Start the mock scheduler."""
        self.started = True
        self.stopped = False

    async def stop(self) -> None:
        """Stop the mock scheduler."""
        self.stopped = True
        self.started = False

    async def refresh_schedules(self) -> None:
        """Refresh schedules (mock - just increments counter)."""
        self.refresh_count += 1

    def add_scheduled_job(
        self,
        client_id: UUID,
        integration_id: UUID,
        cron_expr: str,
    ) -> None:
        """Helper to add a scheduled job for testing."""
        self.scheduled_jobs.append((client_id, integration_id, cron_expr))

    def record_trigger_sync(self, client_id: UUID, integration_id: UUID) -> None:
        """Helper to record a trigger_sync call for testing."""
        self.trigger_sync_calls.append((client_id, integration_id))

    def reset(self) -> None:
        """Reset all state."""
        self.started = False
        self.stopped = False
        self.refresh_count = 0
        self.scheduled_jobs.clear()
        self.trigger_sync_calls.clear()
