"""Tests for API endpoints."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.domain.entities import (
    AvailableIntegration,
    ConnectionConfig,
    SyncJob,
    SyncRule,
    UserIntegration,
    UserIntegrationSettings,
)
from app.domain.enums import (
    IntegrationStatus,
    SyncDirection,
    SyncJobStatus,
    SyncJobTrigger,
    SyncJobType,
)
from app.services.integration_service import IntegrationService
from app.services.settings_service import SettingsService
from app.services.sync_orchestrator import SyncOrchestrator


@pytest.fixture
def sample_integration_id():
    """Generate a sample integration ID."""
    return uuid4()


@pytest.fixture
def sample_client_id():
    """Generate a sample client ID."""
    return uuid4()


@pytest.fixture
def sample_available_integration(sample_integration_id):
    """Create a sample available integration."""
    now = datetime.now(UTC)
    return AvailableIntegration(
        id=sample_integration_id,
        name="QuickBooks Online",
        type="erp",
        description="QuickBooks Online integration",
        supported_entities=["bill", "invoice", "vendor"],
        connection_config=ConnectionConfig(
            authorization_url="https://appcenter.intuit.com/connect/oauth2",
            token_url="https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer",
            scopes=["com.intuit.quickbooks.accounting"],
        ),
        is_active=True,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def sample_user_integration(sample_integration_id, sample_client_id, sample_available_integration):
    """Create a sample user integration."""
    now = datetime.now(UTC)
    return UserIntegration(
        id=uuid4(),
        client_id=sample_client_id,
        integration_id=sample_integration_id,
        status=IntegrationStatus.CONNECTED,
        credentials_encrypted=b"encrypted",
        credentials_key_id="test-key",
        external_account_id="ext-123",
        last_connected_at=now,
        created_at=now,
        updated_at=now,
        integration=sample_available_integration,
    )


@pytest.fixture
def sample_sync_job(sample_integration_id, sample_client_id):
    """Create a sample sync job."""
    now = datetime.now(UTC)
    return SyncJob(
        id=uuid4(),
        client_id=sample_client_id,
        integration_id=sample_integration_id,
        job_type=SyncJobType.FULL_SYNC,
        status=SyncJobStatus.PENDING,
        triggered_by=SyncJobTrigger.USER,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def mock_integration_service():
    """Create a mock integration service."""
    service = AsyncMock(spec=IntegrationService)
    return service


@pytest.fixture
def mock_settings_service():
    """Create a mock settings service."""
    service = AsyncMock(spec=SettingsService)
    return service


@pytest.fixture
def mock_sync_orchestrator():
    """Create a mock sync orchestrator."""
    orchestrator = AsyncMock(spec=SyncOrchestrator)
    return orchestrator


@pytest.fixture
def test_app(
    mock_integration_service,
    mock_settings_service,
    mock_sync_orchestrator,
    sample_client_id,
):
    """Create a test FastAPI app with dependency overrides."""
    from app.api import (
        health_router,
        integrations_router,
        settings_router,
        sync_jobs_router,
    )
    from app.api.integrations import get_client_id as get_client_id_integrations
    from app.api.integrations import get_integration_service
    from app.api.integrations import (
        get_sync_orchestrator as get_sync_orchestrator_integrations,
    )
    from app.api.settings import get_client_id as get_client_id_settings
    from app.api.settings import get_settings_service
    from app.api.sync_jobs import get_client_id as get_client_id_sync
    from app.api.sync_jobs import get_sync_orchestrator

    app = FastAPI()
    app.include_router(health_router)
    app.include_router(integrations_router)
    app.include_router(settings_router)
    app.include_router(sync_jobs_router)

    # Override dependencies
    app.dependency_overrides[get_integration_service] = lambda: mock_integration_service
    app.dependency_overrides[get_settings_service] = lambda: mock_settings_service
    app.dependency_overrides[get_sync_orchestrator] = lambda: mock_sync_orchestrator
    app.dependency_overrides[get_sync_orchestrator_integrations] = lambda: mock_sync_orchestrator
    app.dependency_overrides[get_client_id_integrations] = lambda: sample_client_id
    app.dependency_overrides[get_client_id_settings] = lambda: sample_client_id
    app.dependency_overrides[get_client_id_sync] = lambda: sample_client_id

    return app


@pytest.fixture
def client(test_app):
    """Create test client."""
    return TestClient(test_app)


class TestHealthEndpoints:
    """Test health check endpoints."""

    def test_health_check(self, client):
        """Test basic health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["version"] == "0.1.0"
        assert "timestamp" in data

    def test_liveness_check(self, client):
        """Test liveness endpoint."""
        response = client.get("/health/live")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "alive"


class TestIntegrationsEndpoints:
    """Test integration management endpoints."""

    def test_list_available_integrations(
        self,
        client,
        mock_integration_service,
        sample_available_integration,
    ):
        """Test listing available integrations."""
        mock_integration_service.get_available_integrations.return_value = [
            sample_available_integration
        ]

        response = client.get("/integrations/available")
        assert response.status_code == 200
        data = response.json()
        assert "integrations" in data
        assert len(data["integrations"]) == 1
        assert data["integrations"][0]["name"] == "QuickBooks Online"
        assert data["integrations"][0]["type"] == "erp"

    def test_get_available_integration(
        self,
        client,
        mock_integration_service,
        sample_available_integration,
    ):
        """Test getting a specific available integration."""
        mock_integration_service.get_available_integration.return_value = (
            sample_available_integration
        )

        response = client.get(f"/integrations/available/{sample_available_integration.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "QuickBooks Online"
        assert data["type"] == "erp"
        assert "connection_config" in data

    def test_get_available_integration_not_found(
        self,
        client,
        mock_integration_service,
    ):
        """Test getting non-existent integration returns 404."""
        from app.core.exceptions import NotFoundError

        integration_id = uuid4()
        mock_integration_service.get_available_integration.side_effect = NotFoundError(
            resource_type="Integration",
            resource_id=integration_id,
        )

        response = client.get(f"/integrations/available/{integration_id}")
        assert response.status_code == 404

    def test_list_user_integrations(
        self,
        client,
        mock_integration_service,
        sample_user_integration,
    ):
        """Test listing user's connected integrations."""
        mock_integration_service.get_user_integrations.return_value = [sample_user_integration]

        response = client.get("/integrations")
        assert response.status_code == 200
        data = response.json()
        assert "integrations" in data
        assert len(data["integrations"]) == 1
        assert data["integrations"][0]["status"] == "connected"

    def test_get_user_integration(
        self,
        client,
        mock_integration_service,
        sample_user_integration,
    ):
        """Test getting a specific user integration."""
        mock_integration_service.get_user_integration.return_value = sample_user_integration

        response = client.get(f"/integrations/{sample_user_integration.integration_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "connected"
        assert data["external_account_id"] == "ext-123"

    def test_connect_integration(
        self,
        client,
        mock_integration_service,
        sample_integration_id,
    ):
        """Test starting OAuth connection."""
        mock_integration_service.get_oauth_authorization_url.return_value = (
            "https://oauth.example.com/auth?state=abc"
        )

        response = client.post(
            f"/integrations/{sample_integration_id}/connect",
            json={
                "redirect_uri": "https://app.example.com/callback",
                "state": "abc123",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "authorization_url" in data
        assert "oauth.example.com" in data["authorization_url"]

    def test_oauth_callback(
        self,
        client,
        mock_integration_service,
        sample_user_integration,
    ):
        """Test completing OAuth callback."""
        mock_integration_service.complete_oauth_callback.return_value = sample_user_integration

        response = client.post(
            f"/integrations/{sample_user_integration.integration_id}/callback",
            json={
                "code": "auth_code_123",
                "redirect_uri": "https://app.example.com/callback",
                "state": "valid-csrf-state-token",  # Required for CSRF protection
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "connected"

    def test_disconnect_integration(
        self,
        client,
        mock_integration_service,
        sample_integration_id,
    ):
        """Test disconnecting an integration."""
        mock_integration_service.disconnect_integration.return_value = None

        response = client.delete(f"/integrations/{sample_integration_id}")
        assert response.status_code == 204


class TestSyncJobsEndpoints:
    """Test sync job endpoints."""

    def test_trigger_sync_job(
        self,
        client,
        mock_sync_orchestrator,
        sample_sync_job,
    ):
        """Test triggering a new sync job."""
        mock_sync_orchestrator.trigger_sync.return_value = sample_sync_job

        response = client.post(
            "/sync-jobs",
            json={
                "integration_id": str(sample_sync_job.integration_id),
                "job_type": "full_sync",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "pending"
        assert data["job_type"] == "full_sync"

    def test_list_sync_jobs(
        self,
        client,
        mock_sync_orchestrator,
        sample_sync_job,
    ):
        """Test listing sync jobs."""
        mock_sync_orchestrator.get_jobs_paginated.return_value = ([sample_sync_job], 1)

        response = client.get("/sync-jobs")
        assert response.status_code == 200
        data = response.json()
        assert "jobs" in data
        assert len(data["jobs"]) == 1
        assert data["total"] == 1

    def test_get_sync_job(
        self,
        client,
        mock_sync_orchestrator,
        sample_sync_job,
    ):
        """Test getting a specific sync job."""
        mock_sync_orchestrator.get_job.return_value = sample_sync_job

        response = client.get(f"/sync-jobs/{sample_sync_job.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "pending"

    def test_cancel_sync_job(
        self,
        client,
        mock_sync_orchestrator,
        sample_sync_job,
    ):
        """Test canceling a sync job."""
        cancelled_job = sample_sync_job.model_copy()
        cancelled_job.status = SyncJobStatus.CANCELLED

        mock_sync_orchestrator.cancel_sync_job.return_value = cancelled_job

        response = client.post(f"/sync-jobs/{sample_sync_job.id}/cancel")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "cancelled"

    def test_get_job_records(
        self,
        client,
        mock_sync_orchestrator,
        sample_sync_job,
    ):
        """Test getting record-level sync details for a job."""
        from app.domain.entities import IntegrationHistoryRecord
        from app.domain.enums import RecordSyncStatus

        now = datetime.now(UTC)
        mock_records = [
            IntegrationHistoryRecord(
                id=uuid4(),
                client_id=sample_sync_job.client_id,
                state_record_id=uuid4(),
                integration_id=sample_sync_job.integration_id,
                entity_type="invoice",
                internal_record_id="INV-001",
                external_record_id="QB-12345",
                sync_status=RecordSyncStatus.SYNCED,
                sync_direction=SyncDirection.OUTBOUND,
                job_id=sample_sync_job.id,
                created_at=now,
            ),
            IntegrationHistoryRecord(
                id=uuid4(),
                client_id=sample_sync_job.client_id,
                state_record_id=uuid4(),
                integration_id=sample_sync_job.integration_id,
                entity_type="invoice",
                internal_record_id="INV-002",
                external_record_id=None,
                sync_status=RecordSyncStatus.FAILED,
                sync_direction=SyncDirection.OUTBOUND,
                job_id=sample_sync_job.id,
                error_code="VALIDATION_ERROR",
                error_message="Missing required field",
                created_at=now,
            ),
        ]

        mock_sync_orchestrator.get_job.return_value = sample_sync_job
        mock_sync_orchestrator.get_job_records.return_value = (mock_records, 2)

        response = client.get(f"/sync-jobs/{sample_sync_job.id}/records")
        assert response.status_code == 200
        data = response.json()
        assert "records" in data
        assert len(data["records"]) == 2
        assert data["total"] == 2
        assert data["page"] == 1
        assert data["page_size"] == 50
        assert data["total_pages"] == 1

        # Check first record (synced)
        assert data["records"][0]["sync_status"] == "synced"
        assert data["records"][0]["is_success"] is True
        assert data["records"][0]["external_record_id"] == "QB-12345"

        # Check second record (failed)
        assert data["records"][1]["sync_status"] == "failed"
        assert data["records"][1]["is_success"] is False
        assert data["records"][1]["error_code"] == "VALIDATION_ERROR"

    def test_get_job_records_with_filters(
        self,
        client,
        mock_sync_orchestrator,
        sample_sync_job,
    ):
        """Test getting job records with filters."""
        mock_sync_orchestrator.get_job.return_value = sample_sync_job
        mock_sync_orchestrator.get_job_records.return_value = ([], 0)

        response = client.get(
            f"/sync-jobs/{sample_sync_job.id}/records",
            params={
                "entity_type": "invoice",
                "status": "failed",
                "page": 2,
                "page_size": 20,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["records"] == []
        assert data["total"] == 0
        assert data["page"] == 2
        assert data["page_size"] == 20

    def test_get_job_records_not_found(
        self,
        client,
        mock_sync_orchestrator,
    ):
        """Test getting records for non-existent job returns 404."""
        from app.core.exceptions import NotFoundError

        mock_sync_orchestrator.get_job.side_effect = NotFoundError("SyncJob", "fake-id")

        fake_job_id = uuid4()
        response = client.get(f"/sync-jobs/{fake_job_id}/records")
        assert response.status_code == 404


class TestSettingsEndpoints:
    """Test settings endpoints."""

    def test_get_user_settings(
        self,
        client,
        mock_settings_service,
        sample_integration_id,
    ):
        """Test getting user integration settings."""
        settings = UserIntegrationSettings(
            sync_rules=[
                SyncRule(entity_type="bill", direction=SyncDirection.INBOUND, enabled=True),
                SyncRule(entity_type="vendor", direction=SyncDirection.INBOUND, enabled=True),
            ],
            sync_frequency="0 */6 * * *",
            auto_sync_enabled=True,
        )
        mock_settings_service.get_user_settings.return_value = settings

        response = client.get(f"/integrations/{sample_integration_id}/settings")
        assert response.status_code == 200
        data = response.json()
        assert "sync_rules" in data
        assert len(data["sync_rules"]) == 2
        assert data["auto_sync_enabled"] is True

    def test_update_user_settings(
        self,
        client,
        mock_settings_service,
        sample_integration_id,
    ):
        """Test updating user integration settings."""
        updated_settings = UserIntegrationSettings(
            sync_rules=[
                SyncRule(entity_type="invoice", direction=SyncDirection.OUTBOUND, enabled=True),
            ],
            sync_frequency="0 0 * * *",
            auto_sync_enabled=False,
        )
        mock_settings_service.update_user_settings.return_value = updated_settings

        response = client.put(
            f"/integrations/{sample_integration_id}/settings",
            json={
                "sync_rules": [
                    {"entity_type": "invoice", "direction": "outbound", "enabled": True},
                ],
                "sync_frequency": "0 0 * * *",
                "auto_sync_enabled": False,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["auto_sync_enabled"] is False
        assert data["sync_frequency"] == "0 0 * * *"

    def test_get_default_settings(
        self,
        client,
        mock_settings_service,
        sample_integration_id,
    ):
        """Test getting default integration settings."""
        mock_settings_service.get_system_settings.return_value = None

        response = client.get(f"/integrations/{sample_integration_id}/settings/defaults")
        assert response.status_code == 200
        data = response.json()
        assert data["sync_rules"] == []
        assert data["auto_sync_enabled"] is False
