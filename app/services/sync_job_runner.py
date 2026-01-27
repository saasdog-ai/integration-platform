"""Background worker for processing sync jobs from queue."""

import asyncio
import json
import signal
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.domain.entities import SyncJob, SyncJobMessage
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

    async def start(self) -> None:
        """Start the job runner."""
        if self._running:
            logger.warning("Job runner is already running")
            return

        self._running = True
        self._semaphore = asyncio.Semaphore(self._max_workers)

        logger.info(
            "Starting sync job runner",
            extra={"max_workers": self._max_workers},
        )

        # Set up signal handlers for graceful shutdown
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))

        # Main polling loop
        while self._running:
            try:
                await self._poll_and_process()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    "Error in job runner main loop",
                    extra={"error": str(e)},
                )
                await asyncio.sleep(5)  # Brief pause before retrying

        logger.info("Sync job runner stopped")

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

            task = asyncio.create_task(
                self._process_message(message.body, message.receipt_handle)
            )
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

    async def _process_message(
        self,
        message_body: dict[str, Any],
        receipt_handle: str,
    ) -> None:
        """
        Process a single message.

        Args:
            message_body: The message content.
            receipt_handle: Handle for deleting the message.
        """
        try:
            # Parse message
            job_message = SyncJobMessage(
                job_id=message_body["job_id"],
                client_id=message_body["client_id"],
                integration_id=message_body["integration_id"],
                job_type=SyncJobType(message_body["job_type"]),
                entity_types=message_body.get("entity_types"),
            )

            logger.info(
                "Processing sync job",
                extra={
                    "job_id": str(job_message.job_id),
                    "client_id": str(job_message.client_id),
                    "integration_id": str(job_message.integration_id),
                    "job_type": job_message.job_type.value,
                },
            )

            # Get the job
            job = await self._job_repo.get_job(job_message.job_id)
            if not job:
                logger.error(
                    "Job not found",
                    extra={"job_id": str(job_message.job_id)},
                )
                await self._queue.delete_message(receipt_handle)
                return

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
                return

            # Execute the job
            await self._orchestrator.execute_sync_job(job)

            # Delete message on success
            await self._queue.delete_message(receipt_handle)

            logger.info(
                "Sync job processed successfully",
                extra={"job_id": str(job.id)},
            )

        except Exception as e:
            logger.error(
                "Failed to process sync job",
                extra={
                    "error": str(e),
                    "message_body": message_body,
                },
            )
            # Don't delete message - it will become visible again for retry
            # In production, you'd want dead letter queue after N retries


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
