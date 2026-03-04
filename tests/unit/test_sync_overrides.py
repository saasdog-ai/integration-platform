"""Tests for manual sync overrides (force-sync, do-not-sync) and audit log."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth import AuthenticatedClient
from app.domain.entities import (
    AvailableIntegration,
    ConnectionConfig,
    IntegrationStateRecord,
    UserIntegration,
)
from app.domain.enums import (
    IntegrationStatus,
    RecordSyncStatus,
    SyncDirection,
)
from tests.mocks.repositories import MockIntegrationStateRepository

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def client_id():
    return uuid4()


@pytest.fixture
def integration_id():
    return uuid4()


@pytest.fixture
def state_repo():
    return MockIntegrationStateRepository()


@pytest.fixture
def mock_integration_service(client_id, integration_id):
    service = AsyncMock()
    now = datetime.now(UTC)
    service.get_user_integration.return_value = UserIntegration(
        id=uuid4(),
        client_id=client_id,
        integration_id=integration_id,
        status=IntegrationStatus.CONNECTED,
        created_at=now,
        updated_at=now,
        integration=AvailableIntegration(
            id=integration_id,
            name="Test Integration",
            type="erp",
            supported_entities=["bill", "vendor"],
            connection_config=ConnectionConfig(
                authorization_url="https://example.com/auth",
                token_url="https://example.com/token",
            ),
            created_at=now,
            updated_at=now,
        ),
    )
    return service


@pytest.fixture
def authenticated_client(client_id):
    return AuthenticatedClient(client_id=client_id, user_id="test-user-123")


@pytest.fixture
def test_app(mock_integration_service, state_repo, client_id, authenticated_client):
    from app.api import integrations_router
    from app.api.integrations import get_client_id as get_client_id_dep
    from app.api.integrations import (
        get_current_client,
        get_integration_service,
        get_state_repository,
    )

    app = FastAPI()
    app.include_router(integrations_router)

    app.dependency_overrides[get_integration_service] = lambda: mock_integration_service
    app.dependency_overrides[get_state_repository] = lambda: state_repo
    app.dependency_overrides[get_client_id_dep] = lambda: client_id
    app.dependency_overrides[get_current_client] = lambda: authenticated_client

    return app


@pytest.fixture
def client(test_app):
    return TestClient(test_app)


def _make_state_record(
    client_id,
    integration_id,
    entity_type="bill",
    sync_status=RecordSyncStatus.FAILED,
    internal_record_id=None,
    external_record_id=None,
    internal_version_id=3,
    external_version_id=5,
    last_sync_version_id=2,
    error_message="Xero API error",
    do_not_sync=False,
) -> IntegrationStateRecord:
    now = datetime.now(UTC)
    return IntegrationStateRecord(
        id=uuid4(),
        client_id=client_id,
        integration_id=integration_id,
        entity_type=entity_type,
        internal_record_id=internal_record_id or str(uuid4()),
        external_record_id=external_record_id or str(uuid4()),
        sync_status=sync_status,
        sync_direction=SyncDirection.OUTBOUND,
        internal_version_id=internal_version_id,
        external_version_id=external_version_id,
        last_sync_version_id=last_sync_version_id,
        error_code="API_ERROR" if sync_status == RecordSyncStatus.FAILED else None,
        error_message=error_message if sync_status == RecordSyncStatus.FAILED else None,
        do_not_sync=do_not_sync,
        created_at=now,
        updated_at=now,
    )


# =============================================================================
# Force-Sync Tests
# =============================================================================


class TestForceSync:
    """Tests for POST /integrations/{id}/records/force-sync."""

    def test_force_sync_clears_errors_and_equalizes_vectors(
        self, client, state_repo, client_id, integration_id
    ):
        """Force-sync should clear errors and equalize version vectors."""
        record = _make_state_record(
            client_id, integration_id,
            internal_version_id=3, external_version_id=5, last_sync_version_id=2,
        )
        state_repo._records[(client_id, record.id)] = record

        response = client.post(
            f"/integrations/{integration_id}/records/force-sync",
            json={"state_ids": [str(record.id)]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["records_updated"] == 1
        assert data["records_skipped"] == 0

        # Verify the record state
        updated = state_repo._records[(client_id, record.id)]
        assert updated.sync_status == RecordSyncStatus.SYNCED
        assert updated.error_code is None
        assert updated.error_message is None
        assert updated.error_details is None
        assert updated.internal_version_id == 5  # max(3, 5)
        assert updated.external_version_id == 5
        assert updated.last_sync_version_id == 5
        assert updated.force_synced_at is not None

    def test_force_sync_skips_already_synced(
        self, client, state_repo, client_id, integration_id
    ):
        """Force-sync should skip records that are already synced."""
        record = _make_state_record(
            client_id, integration_id,
            sync_status=RecordSyncStatus.SYNCED,
            error_message=None,
        )
        state_repo._records[(client_id, record.id)] = record

        response = client.post(
            f"/integrations/{integration_id}/records/force-sync",
            json={"state_ids": [str(record.id)]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["records_updated"] == 0
        assert data["records_skipped"] == 1
        assert "synced" in data["skipped_details"][0]["reason"]

    def test_force_sync_handles_conflict_status(
        self, client, state_repo, client_id, integration_id
    ):
        """Force-sync should work on conflict records too."""
        record = _make_state_record(
            client_id, integration_id,
            sync_status=RecordSyncStatus.CONFLICT,
            error_message=None,
        )
        state_repo._records[(client_id, record.id)] = record

        response = client.post(
            f"/integrations/{integration_id}/records/force-sync",
            json={"state_ids": [str(record.id)]},
        )

        assert response.status_code == 200
        assert response.json()["records_updated"] == 1

    def test_force_sync_skips_not_found(
        self, client, state_repo, client_id, integration_id
    ):
        """Force-sync should skip records that don't exist."""
        fake_id = uuid4()
        response = client.post(
            f"/integrations/{integration_id}/records/force-sync",
            json={"state_ids": [str(fake_id)]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["records_updated"] == 0
        assert data["records_skipped"] == 1
        assert data["skipped_details"][0]["reason"] == "Record not found"

    def test_force_sync_bulk(self, client, state_repo, client_id, integration_id):
        """Force-sync should handle multiple records in one request."""
        records = [
            _make_state_record(client_id, integration_id)
            for _ in range(3)
        ]
        for r in records:
            state_repo._records[(client_id, r.id)] = r

        response = client.post(
            f"/integrations/{integration_id}/records/force-sync",
            json={"state_ids": [str(r.id) for r in records]},
        )

        assert response.status_code == 200
        assert response.json()["records_updated"] == 3

    def test_force_sync_writes_audit_log(
        self, client, state_repo, client_id, integration_id
    ):
        """Force-sync should write an audit log entry."""
        record = _make_state_record(client_id, integration_id)
        state_repo._records[(client_id, record.id)] = record

        client.post(
            f"/integrations/{integration_id}/records/force-sync",
            json={"state_ids": [str(record.id)]},
        )

        assert len(state_repo._audit_log) == 1
        entry = state_repo._audit_log[0]
        assert entry.action == "force_sync"
        assert entry.performed_by == "test-user-123"
        assert entry.integration_id == integration_id

    def test_force_sync_by_internal_record_ids(
        self, client, state_repo, client_id, integration_id
    ):
        """Force-sync should resolve internal_record_ids to state IDs."""
        record = _make_state_record(
            client_id, integration_id,
            internal_record_id="BILL-001",
        )
        state_repo._records[(client_id, record.id)] = record

        response = client.post(
            f"/integrations/{integration_id}/records/force-sync",
            json={
                "entity_type": "bill",
                "internal_record_ids": ["BILL-001"],
            },
        )

        assert response.status_code == 200
        assert response.json()["records_updated"] == 1

    def test_force_sync_by_external_record_ids(
        self, client, state_repo, client_id, integration_id
    ):
        """Force-sync should resolve external_record_ids to state IDs."""
        record = _make_state_record(
            client_id, integration_id,
            external_record_id="xero-guid-abc",
        )
        state_repo._records[(client_id, record.id)] = record

        response = client.post(
            f"/integrations/{integration_id}/records/force-sync",
            json={
                "entity_type": "bill",
                "external_record_ids": ["xero-guid-abc"],
            },
        )

        assert response.status_code == 200
        assert response.json()["records_updated"] == 1


# =============================================================================
# Do-Not-Sync Tests
# =============================================================================


class TestDoNotSync:
    """Tests for POST /integrations/{id}/records/do-not-sync."""

    def test_toggle_on_sets_flag_and_clears_errors(
        self, client, state_repo, client_id, integration_id
    ):
        """Toggling do-not-sync ON should set the flag and clear errors."""
        record = _make_state_record(client_id, integration_id)
        state_repo._records[(client_id, record.id)] = record

        response = client.post(
            f"/integrations/{integration_id}/records/do-not-sync",
            json={"state_ids": [str(record.id)], "do_not_sync": True},
        )

        assert response.status_code == 200
        assert response.json()["records_updated"] == 1

        updated = state_repo._records[(client_id, record.id)]
        assert updated.do_not_sync is True
        assert updated.error_code is None
        assert updated.error_message is None

    def test_toggle_off_sets_pending_if_version_mismatch(
        self, client, state_repo, client_id, integration_id
    ):
        """Toggling do-not-sync OFF should set status to PENDING if versions mismatch."""
        record = _make_state_record(
            client_id, integration_id,
            sync_status=RecordSyncStatus.SYNCED,
            internal_version_id=5,
            external_version_id=3,
            last_sync_version_id=3,
            do_not_sync=True,
            error_message=None,
        )
        state_repo._records[(client_id, record.id)] = record

        response = client.post(
            f"/integrations/{integration_id}/records/do-not-sync",
            json={"state_ids": [str(record.id)], "do_not_sync": False},
        )

        assert response.status_code == 200
        updated = state_repo._records[(client_id, record.id)]
        assert updated.do_not_sync is False
        assert updated.sync_status == RecordSyncStatus.PENDING

    def test_toggle_off_keeps_status_if_in_sync(
        self, client, state_repo, client_id, integration_id
    ):
        """Toggling OFF should keep SYNCED status if versions match."""
        record = _make_state_record(
            client_id, integration_id,
            sync_status=RecordSyncStatus.SYNCED,
            internal_version_id=5,
            external_version_id=5,
            last_sync_version_id=5,
            do_not_sync=True,
            error_message=None,
        )
        state_repo._records[(client_id, record.id)] = record

        response = client.post(
            f"/integrations/{integration_id}/records/do-not-sync",
            json={"state_ids": [str(record.id)], "do_not_sync": False},
        )

        assert response.status_code == 200
        updated = state_repo._records[(client_id, record.id)]
        assert updated.sync_status == RecordSyncStatus.SYNCED

    def test_do_not_sync_writes_audit_log(
        self, client, state_repo, client_id, integration_id
    ):
        """Do-not-sync toggle should write an audit log entry."""
        record = _make_state_record(client_id, integration_id)
        state_repo._records[(client_id, record.id)] = record

        client.post(
            f"/integrations/{integration_id}/records/do-not-sync",
            json={"state_ids": [str(record.id)], "do_not_sync": True},
        )

        assert len(state_repo._audit_log) == 1
        entry = state_repo._audit_log[0]
        assert entry.action == "do_not_sync_enabled"
        assert entry.performed_by == "test-user-123"

    def test_do_not_sync_disabled_audit_log(
        self, client, state_repo, client_id, integration_id
    ):
        """Toggling OFF should write 'do_not_sync_disabled' action."""
        record = _make_state_record(
            client_id, integration_id,
            sync_status=RecordSyncStatus.SYNCED,
            internal_version_id=5,
            external_version_id=5,
            last_sync_version_id=5,
            do_not_sync=True,
            error_message=None,
        )
        state_repo._records[(client_id, record.id)] = record

        client.post(
            f"/integrations/{integration_id}/records/do-not-sync",
            json={"state_ids": [str(record.id)], "do_not_sync": False},
        )

        assert state_repo._audit_log[0].action == "do_not_sync_disabled"

    def test_do_not_sync_bulk(self, client, state_repo, client_id, integration_id):
        """Do-not-sync should handle multiple records."""
        records = [
            _make_state_record(client_id, integration_id)
            for _ in range(3)
        ]
        for r in records:
            state_repo._records[(client_id, r.id)] = r

        response = client.post(
            f"/integrations/{integration_id}/records/do-not-sync",
            json={
                "state_ids": [str(r.id) for r in records],
                "do_not_sync": True,
            },
        )

        assert response.status_code == 200
        assert response.json()["records_updated"] == 3


# =============================================================================
# Record Selector Validation Tests
# =============================================================================


class TestRecordSelectorValidation:
    """Tests for RecordSelector Pydantic validation."""

    def test_no_selector_provided(self, client, integration_id):
        """Should reject when no selector is provided."""
        response = client.post(
            f"/integrations/{integration_id}/records/force-sync",
            json={},
        )
        assert response.status_code == 422

    def test_multiple_selectors_provided(self, client, integration_id):
        """Should reject when multiple selectors are provided."""
        response = client.post(
            f"/integrations/{integration_id}/records/force-sync",
            json={
                "state_ids": [str(uuid4())],
                "internal_record_ids": ["BILL-001"],
                "entity_type": "bill",
            },
        )
        assert response.status_code == 422

    def test_internal_ids_without_entity_type(self, client, integration_id):
        """Should reject internal_record_ids without entity_type."""
        response = client.post(
            f"/integrations/{integration_id}/records/force-sync",
            json={"internal_record_ids": ["BILL-001"]},
        )
        assert response.status_code == 422

    def test_external_ids_without_entity_type(self, client, integration_id):
        """Should reject external_record_ids without entity_type."""
        response = client.post(
            f"/integrations/{integration_id}/records/force-sync",
            json={"external_record_ids": ["xero-guid"]},
        )
        assert response.status_code == 422


# =============================================================================
# Browse Records Tests
# =============================================================================


class TestBrowseRecords:
    """Tests for GET /integrations/{id}/records."""

    def test_browse_all_records(self, client, state_repo, client_id, integration_id):
        """Should return all records for an integration."""
        records = [
            _make_state_record(client_id, integration_id, sync_status=RecordSyncStatus.FAILED),
            _make_state_record(client_id, integration_id, sync_status=RecordSyncStatus.SYNCED, error_message=None),
        ]
        for r in records:
            state_repo._records[(client_id, r.id)] = r

        response = client.get(f"/integrations/{integration_id}/records")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["records"]) == 2

    def test_browse_filter_by_status(self, client, state_repo, client_id, integration_id):
        """Should filter records by sync_status."""
        r1 = _make_state_record(client_id, integration_id, sync_status=RecordSyncStatus.FAILED)
        r2 = _make_state_record(client_id, integration_id, sync_status=RecordSyncStatus.SYNCED, error_message=None)
        state_repo._records[(client_id, r1.id)] = r1
        state_repo._records[(client_id, r2.id)] = r2

        response = client.get(
            f"/integrations/{integration_id}/records?sync_status=failed"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["records"][0]["sync_status"] == "failed"

    def test_browse_filter_by_do_not_sync(
        self, client, state_repo, client_id, integration_id
    ):
        """Should filter records by do_not_sync flag."""
        r1 = _make_state_record(client_id, integration_id, do_not_sync=True)
        r2 = _make_state_record(client_id, integration_id, do_not_sync=False)
        state_repo._records[(client_id, r1.id)] = r1
        state_repo._records[(client_id, r2.id)] = r2

        response = client.get(
            f"/integrations/{integration_id}/records?do_not_sync=true"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["records"][0]["do_not_sync"] is True

    def test_browse_includes_new_fields(
        self, client, state_repo, client_id, integration_id
    ):
        """Response should include do_not_sync and force_synced_at fields."""
        record = _make_state_record(client_id, integration_id)
        state_repo._records[(client_id, record.id)] = record

        response = client.get(f"/integrations/{integration_id}/records")

        data = response.json()
        rec = data["records"][0]
        assert "do_not_sync" in rec
        assert "force_synced_at" in rec

    def test_browse_pagination(self, client, state_repo, client_id, integration_id):
        """Should paginate records correctly."""
        for _ in range(5):
            r = _make_state_record(client_id, integration_id)
            state_repo._records[(client_id, r.id)] = r

        response = client.get(
            f"/integrations/{integration_id}/records?page=1&page_size=2"
        )

        data = response.json()
        assert data["total"] == 5
        assert len(data["records"]) == 2
        assert data["total_pages"] == 3


# =============================================================================
# Sync Engine Guard Tests (do-not-sync in get_records_by_status)
# =============================================================================


class TestSyncEngineGuards:
    """Tests for do-not-sync guards in the sync engine."""

    @pytest.mark.asyncio
    async def test_get_records_by_status_excludes_do_not_sync(self):
        """get_records_by_status should exclude do-not-sync records."""
        repo = MockIntegrationStateRepository()
        cid = uuid4()
        iid = uuid4()

        r1 = _make_state_record(cid, iid, sync_status=RecordSyncStatus.PENDING, error_message=None)
        r1.internal_version_id = 2
        r1.last_sync_version_id = 1
        r2 = _make_state_record(
            cid, iid, sync_status=RecordSyncStatus.PENDING, do_not_sync=True, error_message=None,
        )
        r2.internal_version_id = 2
        r2.last_sync_version_id = 1
        repo._records[(cid, r1.id)] = r1
        repo._records[(cid, r2.id)] = r2

        results = await repo.get_records_by_status(
            cid, iid, "bill", RecordSyncStatus.PENDING
        )

        assert len(results) == 1
        assert results[0].id == r1.id

    @pytest.mark.asyncio
    async def test_get_pending_records_excludes_do_not_sync(self):
        """get_pending_records should also exclude do-not-sync records."""
        repo = MockIntegrationStateRepository()
        cid = uuid4()
        iid = uuid4()

        r1 = _make_state_record(cid, iid, sync_status=RecordSyncStatus.PENDING, error_message=None)
        r2 = _make_state_record(
            cid, iid, sync_status=RecordSyncStatus.PENDING, do_not_sync=True, error_message=None,
        )
        repo._records[(cid, r1.id)] = r1
        repo._records[(cid, r2.id)] = r2

        results = await repo.get_pending_records(cid, iid, "bill")

        assert len(results) == 1
        assert results[0].id == r1.id
