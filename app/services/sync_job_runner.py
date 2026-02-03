"""Background worker for processing sync jobs from queue."""

import asyncio
import signal
import time
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.domain.entities import QueueMessage, SyncJob, SyncJobMessage
from app.domain.enums import SyncJobStatus, SyncJobType
from app.domain.interfaces import (
    AdapterFactoryInterface,
    EncryptionServiceInterface,
    IntegrationRepositoryInterface,
    IntegrationStateRepositoryInterface,
    MessageQueueInterface,
    SyncJobRepositoryInterface,
)
from app.services.sync_orchestrator import SyncOrchestrator

logger = get_logger(__name__)

# Backpressure settings
BACKPRESSURE_ERROR_THRESHOLD = 5  # Number of consecutive errors to trigger backpressure
BACKPRESSURE_MAX_DELAY = 60  # Maximum delay in seconds during backpressure
BACKPRESSURE_BASE_DELAY = 2  # Base delay for exponential backoff

# Stuck job check interval (in seconds)
STUCK_JOB_CHECK_INTERVAL = 300  # Check every 5 minutes

# Pending job recovery interval (in seconds)
PENDING_RECOVERY_INTERVAL = 60  # Check every 1 minute

# History cleanup interval (in seconds)
HISTORY_CLEANUP_INTERVAL = 3600  # Check every 1 hour


class SyncJobRunner:
    """
    Background worker that consumes sync jobs from the queue.

    This runner polls the message queue for sync job messages and
    processes them using the SyncOrchestrator.
    """

    def __init__(
        self,
        queue: MessageQueueInterface,
        integration_repo: IntegrationRepositoryInterface,
        job_repo: SyncJobRepositoryInterface,
        state_repo: IntegrationStateRepositoryInterface,
        encryption_service: EncryptionServiceInterface,
        adapter_factory: AdapterFactoryInterface,
        max_workers: int | None = None,
    ) -> None:
        """
        Initialize sync job runner.

        Args:
            queue: Message queue to consume jobs from.
            integration_repo: Repository for integration data.
            job_repo: Repository for sync job data.
            state_repo: Repository for integration state data.
            encryption_service: Service for credential encryption.
            adapter_factory: Factory for creating integration adapters.
            max_workers: Maximum concurrent workers.
        """
        settings = get_settings()
        self._queue = queue
        self._max_workers = max_workers or settings.job_runner_max_workers
        self._running = False
        self._semaphore: asyncio.Semaphore | None = None
        self._tasks: set[asyncio.Task] = set()

        # Backpressure state
        self._consecutive_errors = 0
        self._backpressure_until: float = 0

        # Stuck job monitoring
        self._last_stuck_job_check: float = 0

        # Pending job recovery
        self._last_pending_recovery: float = 0

        # History cleanup
        self._last_history_cleanup: float = 0

        # Create orchestrator
        self._orchestrator = SyncOrchestrator(
            integration_repo=integration_repo,
            job_repo=job_repo,
            state_repo=state_repo,
            queue=queue,
            encryption_service=encryption_service,
            adapter_factory=adapter_factory,
        )
        self._job_repo = job_repo
        self._state_repo = state_repo
        self._integration_repo = integration_repo

    async def start(self) -> None:
        """Start the job runner."""
        if self._running:
            logger.warning("Job runner is already running")
            return

        settings = get_settings()

        # Check global kill switch
        if settings.sync_globally_disabled:
            logger.warning("Sync is globally disabled via feature flag - job runner not starting")
            return

        self._running = True
        self._semaphore = asyncio.Semaphore(self._max_workers)

        logger.info(
            "Starting sync job runner",
            extra={"max_workers": self._max_workers},
        )

        # Set up signal handlers for graceful shutdown.
        # Wrapped in try/except because this can fail under uvicorn --reload
        # or when not running in the main thread. The lifespan handler in
        # main.py already handles shutdown via task cancellation.
        try:
            loop = asyncio.get_event_loop()
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))
        except (RuntimeError, ValueError):
            logger.debug("Could not set signal handlers — relying on lifespan shutdown")

        # Recover any orphaned pending jobs (lost from in-memory queue on restart)
        await self._recover_pending_jobs()

        # Main polling loop
        while self._running:
            try:
                # Check for stuck jobs periodically
                await self._check_stuck_jobs()

                # Recover orphaned pending jobs periodically
                await self._recover_pending_jobs_periodic()

                # Cleanup old history entries periodically
                await self._cleanup_old_history()

                # Apply backpressure if needed
                if self._backpressure_until > time.time():
                    delay = min(
                        self._backpressure_until - time.time(),
                        BACKPRESSURE_MAX_DELAY,
                    )
                    logger.warning(
                        "Backpressure active, delaying polling",
                        extra={
                            "delay_seconds": delay,
                            "consecutive_errors": self._consecutive_errors,
                        },
                    )
                    await asyncio.sleep(delay)

                await self._poll_and_process()

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._record_error()
                logger.error(
                    "Error in job runner main loop",
                    extra={"error": str(e), "consecutive_errors": self._consecutive_errors},
                )
                await asyncio.sleep(5)  # Brief pause before retrying

        logger.info("Sync job runner stopped")

    def _record_error(self) -> None:
        """Record an error and potentially trigger backpressure."""
        self._consecutive_errors += 1
        if self._consecutive_errors >= BACKPRESSURE_ERROR_THRESHOLD:
            # Exponential backoff with jitter
            import random

            delay = min(
                BACKPRESSURE_BASE_DELAY
                ** (self._consecutive_errors - BACKPRESSURE_ERROR_THRESHOLD + 1),
                BACKPRESSURE_MAX_DELAY,
            )
            delay = delay * (0.5 + random.random())  # Add jitter
            self._backpressure_until = time.time() + delay
            logger.warning(
                "Backpressure triggered due to consecutive errors",
                extra={"consecutive_errors": self._consecutive_errors, "backoff_seconds": delay},
            )

    def _record_success(self) -> None:
        """Record a success and reset backpressure."""
        self._consecutive_errors = 0
        self._backpressure_until = 0

    async def _check_stuck_jobs(self) -> None:
        """Check for and terminate stuck jobs."""
        settings = get_settings()

        # Skip if termination is disabled
        if not settings.job_termination_enabled:
            return

        # Rate limit stuck job checks
        now = time.time()
        if now - self._last_stuck_job_check < STUCK_JOB_CHECK_INTERVAL:
            return

        self._last_stuck_job_check = now

        try:
            stuck_jobs = await self._job_repo.get_stuck_jobs(
                stuck_threshold_minutes=settings.job_stuck_timeout_minutes
            )

            for job in stuck_jobs:
                logger.warning(
                    "Terminating stuck job",
                    extra={
                        "job_id": str(job.id),
                        "client_id": str(job.client_id),
                        "started_at": job.started_at.isoformat() if job.started_at else None,
                    },
                )
                await self._job_repo.terminate_stuck_job(
                    job.id,
                    reason=f"Job exceeded maximum runtime of {settings.job_stuck_timeout_minutes} minutes",
                )

            if stuck_jobs:
                logger.info(
                    "Terminated stuck jobs",
                    extra={"count": len(stuck_jobs)},
                )
        except Exception as e:
            logger.error(
                "Failed to check/terminate stuck jobs",
                extra={"error": str(e)},
            )

    async def _cleanup_old_history(self) -> None:
        """Periodically delete old integration history entries."""
        now = time.time()
        if now - self._last_history_cleanup < HISTORY_CLEANUP_INTERVAL:
            return

        self._last_history_cleanup = now

        try:
            settings = get_settings()
            deleted = await self._state_repo.cleanup_old_history(
                retention_days=settings.integration_history_retention_days,
            )
            if deleted > 0:
                logger.info(
                    "Cleaned up old history entries",
                    extra={
                        "deleted": deleted,
                        "retention_days": settings.integration_history_retention_days,
                    },
                )
        except Exception as e:
            logger.error(
                "Failed to cleanup old history",
                extra={"error": str(e)},
            )

    async def _recover_pending_jobs(self) -> None:
        """Re-enqueue orphaned pending jobs whose queue messages were lost.

        This handles the case where the in-memory queue loses messages on
        server restart while jobs remain in PENDING status in the database.
        """
        try:
            pending_jobs = await self._job_repo.get_pending_jobs(stale_seconds=30)
            if not pending_jobs:
                return

            logger.info(
                "Recovering orphaned pending jobs",
                extra={"count": len(pending_jobs)},
            )
            for job in pending_jobs:
                try:
                    message = SyncJobMessage(
                        job_id=job.id,
                        client_id=job.client_id,
                        integration_id=job.integration_id,
                        job_type=job.job_type,
                        entity_types=job.job_params.get("entity_types") if job.job_params else None,
                    )
                    await self._queue.send_message(message.model_dump(mode="json"))
                    logger.info(
                        "Re-enqueued pending job",
                        extra={"job_id": str(job.id)},
                    )
                except Exception as e:
                    logger.error(
                        "Failed to re-enqueue pending job",
                        extra={"job_id": str(job.id), "error": str(e)},
                    )
        except Exception as e:
            logger.error(
                "Failed to recover pending jobs",
                extra={"error": str(e)},
            )

    async def _recover_pending_jobs_periodic(self) -> None:
        """Periodically re-enqueue orphaned pending jobs.

        Complements the startup recovery by catching jobs whose queue messages
        were lost after the runner was already running (e.g. due to transient
        errors or internal queue issues).
        """
        now = time.time()
        if now - self._last_pending_recovery < PENDING_RECOVERY_INTERVAL:
            return

        self._last_pending_recovery = now
        await self._recover_pending_jobs()

    async def stop(self) -> None:
        """Stop the job runner gracefully."""
        if not self._running:
            return

        logger.info("Stopping sync job runner...")
        self._running = False

        # Wait for in-flight tasks to complete
        if self._tasks:
            logger.info(
                "Waiting for in-flight tasks",
                extra={"count": len(self._tasks)},
            )
            await asyncio.gather(*self._tasks, return_exceptions=True)

    async def _poll_and_process(self) -> None:
        """Poll for messages and process them."""
        settings = get_settings()

        # Receive messages with long polling
        messages = await self._queue.receive_messages(
            max_messages=min(self._max_workers, 10),
            wait_time_seconds=settings.queue_wait_time_seconds,
        )

        if not messages:
            return

        logger.debug(
            "Received messages from queue",
            extra={"count": len(messages)},
        )

        # Process messages concurrently
        for message in messages:
            # Acquire semaphore to limit concurrency
            await self._semaphore.acquire()

            task = asyncio.create_task(self._process_message(message))
            self._tasks.add(task)
            task.add_done_callback(self._task_done)

    def _task_done(self, task: asyncio.Task) -> None:
        """Callback when a task completes."""
        self._tasks.discard(task)
        if self._semaphore:
            self._semaphore.release()

        # Log any exceptions
        try:
            task.result()
        except Exception as e:
            logger.error(
                "Task failed with exception",
                extra={"error": str(e)},
            )

    def _validate_and_parse_message(
        self,
        message: QueueMessage,
    ) -> SyncJobMessage | None:
        """Validate message fields and parse into SyncJobMessage.

        Returns None for any malformed message (caller should delete and return).
        """
        message_body = message.body

        # Validate required message fields before parsing
        required_fields = ["job_id", "client_id", "integration_id", "job_type"]
        missing_fields = [f for f in required_fields if f not in message_body]
        if missing_fields:
            logger.error(
                "Malformed message - missing required fields",
                extra={
                    "message_id": message.message_id,
                    "missing_fields": missing_fields,
                    "message_keys": list(message_body.keys()),
                },
            )
            return None

        # Validate UUID format for ID fields
        from uuid import UUID

        try:
            job_id = UUID(str(message_body["job_id"]))
            client_id = UUID(str(message_body["client_id"]))
            integration_id = UUID(str(message_body["integration_id"]))
        except (ValueError, TypeError) as e:
            logger.error(
                "Malformed message - invalid UUID format",
                extra={
                    "message_id": message.message_id,
                    "error": str(e),
                },
            )
            return None

        # Validate job_type enum value
        try:
            job_type = SyncJobType(message_body["job_type"])
        except ValueError:
            logger.error(
                "Malformed message - invalid job_type",
                extra={
                    "message_id": message.message_id,
                    "job_type": message_body["job_type"],
                    "valid_types": [t.value for t in SyncJobType],
                },
            )
            return None

        return SyncJobMessage(
            job_id=job_id,
            client_id=client_id,
            integration_id=integration_id,
            job_type=job_type,
            entity_types=message_body.get("entity_types"),
        )

    async def _check_job_ready_for_execution(
        self,
        job_message: SyncJobMessage,
        receipt_handle: str,
        settings: Any,
    ) -> SyncJob | None:
        """Look up job and verify it is ready to execute.

        Returns the SyncJob if ready, or None if the message was handled
        (deleted from queue) because the job is not actionable.
        Note: global kill switch check stays in the caller (different behavior:
        message is NOT deleted when globally disabled).
        """
        # Get the job
        job = await self._job_repo.get_job(job_message.job_id)
        if not job:
            logger.error(
                "Job not found",
                extra={"job_id": str(job_message.job_id)},
            )
            await self._queue.delete_message(receipt_handle)
            return None

        # Check if job is still pending (not cancelled)
        if job.status != SyncJobStatus.PENDING:
            logger.info(
                "Skipping job - not pending",
                extra={
                    "job_id": str(job.id),
                    "status": job.status.value,
                },
            )
            await self._queue.delete_message(receipt_handle)
            return None

        # Check if integration is disabled via feature flag
        integration = await self._integration_repo.get_available_integration(job.integration_id)
        if integration and integration.name in settings.disabled_integrations:
            logger.warning(
                "Integration disabled via feature flag - skipping job",
                extra={
                    "job_id": str(job.id),
                    "integration": integration.name,
                },
            )
            # Mark job as cancelled instead of leaving in queue
            await self._job_repo.update_job_status(
                job.id,
                SyncJobStatus.CANCELLED,
                error_code="INTEGRATION_DISABLED",
                error_message=f"Integration '{integration.name}' is currently disabled",
            )
            await self._queue.delete_message(receipt_handle)
            return None

        return job

    async def _handle_message_failure(
        self,
        message: QueueMessage,
        receipt_handle: str,
        receive_count: int,
        error: Exception,
    ) -> None:
        """Log error, record backpressure, and route to DLQ if max retries exceeded."""
        error_msg = str(error)
        self._record_error()
        logger.error(
            "Failed to process sync job",
            extra={
                "error": error_msg,
                "message_body": message.body,
                "receive_count": receive_count,
                "consecutive_errors": self._consecutive_errors,
            },
        )

        # Send to DLQ after failure
        # Note: The memory queue auto-moves to DLQ after max_receive_count,
        # but we can also explicitly send on catastrophic failures
        settings = get_settings()
        if receive_count >= settings.queue_max_receive_count:
            logger.warning(
                "Moving message to DLQ after max retries",
                extra={
                    "message_id": message.message_id,
                    "receive_count": receive_count,
                    "max_receive_count": settings.queue_max_receive_count,
                },
            )
            await self._queue.send_to_dlq(message, error_msg)
            await self._queue.delete_message(receipt_handle)

        # Don't delete message - it will become visible again for retry
        # After max_receive_count, the queue will auto-move to DLQ

    async def _process_message(
        self,
        message: QueueMessage,
    ) -> None:
        """
        Process a single message.

        Args:
            message: The queue message to process.
        """
        receipt_handle = message.receipt_handle
        receive_count = int(message.attributes.get("ApproximateReceiveCount", 1))
        settings = get_settings()

        try:
            job_message = self._validate_and_parse_message(message)
            if job_message is None:
                await self._queue.delete_message(receipt_handle)
                return

            logger.info(
                "Processing sync job",
                extra={
                    "job_id": str(job_message.job_id),
                    "client_id": str(job_message.client_id),
                    "integration_id": str(job_message.integration_id),
                    "job_type": job_message.job_type.value,
                    "receive_count": receive_count,
                },
            )

            # Check global kill switch
            if settings.sync_globally_disabled:
                logger.warning(
                    "Sync globally disabled - skipping job",
                    extra={"job_id": str(job_message.job_id)},
                )
                # Don't delete - leave for retry when feature flag is cleared
                return

            job = await self._check_job_ready_for_execution(
                job_message,
                receipt_handle,
                settings,
            )
            if job is None:
                return

            # Execute the job
            await self._orchestrator.execute_sync_job(job)

            # Delete message on success
            await self._queue.delete_message(receipt_handle)
            self._record_success()

            logger.info(
                "Sync job processed successfully",
                extra={"job_id": str(job.id)},
            )

        except Exception as e:
            await self._handle_message_failure(
                message,
                receipt_handle,
                receive_count,
                e,
            )


async def run_job_runner() -> None:
    """Entry point for running the job runner as a standalone process."""
    from app.core.dependency_injection import get_container
    from app.infrastructure.adapters.factory import get_adapter_factory

    settings = get_settings()

    if not settings.job_runner_enabled:
        logger.info("Job runner is disabled")
        return

    container = get_container()

    runner = SyncJobRunner(
        queue=container.message_queue,
        integration_repo=container.integration_repository,
        job_repo=container.sync_job_repository,
        state_repo=container.integration_state_repository,
        encryption_service=container.encryption_service,
        adapter_factory=get_adapter_factory(),
    )

    await runner.start()


if __name__ == "__main__":
    asyncio.run(run_job_runner())
