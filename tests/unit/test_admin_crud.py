"""Tests for admin CRUD endpoints for available integrations."""

from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.admin import get_integration_repository, router
from app.domain.entities import AvailableIntegration
from tests.mocks.repositories import MockIntegrationRepository


@pytest.fixture
def mock_repo() -> MockIntegrationRepository:
    repo = MockIntegrationRepository()
    yield repo
    repo.clear()


@pytest.fixture
def client(mock_repo: MockIntegrationRepository) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_integration_repository] = lambda: mock_repo
    return TestClient(app)


@pytest.fixture
def seeded_integration(mock_repo: MockIntegrationRepository) -> AvailableIntegration:
    return mock_repo.seed_available_integration(
        name="QuickBooks Online",
        type="erp",
        supported_entities=["vendor", "bill"],
    )


# =============================================================================
# POST /admin/integrations/available — Create
# =============================================================================


class TestCreateAvailableIntegration:
    def test_create_success(self, client: TestClient) -> None:
        response = client.post(
            "/admin/integrations/available",
            json={
                "name": "Xero",
                "type": "erp",
                "description": "Xero accounting",
                "supported_entities": ["vendor", "bill"],
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Xero"
        assert data["type"] == "erp"
        assert data["description"] == "Xero accounting"
        assert data["supported_entities"] == ["vendor", "bill"]
        assert data["is_active"] is True
        assert "id" in data

    def test_create_with_is_active_false(self, client: TestClient) -> None:
        response = client.post(
            "/admin/integrations/available",
            json={
                "name": "Draft Integration",
                "type": "crm",
                "is_active": False,
            },
        )
        assert response.status_code == 201
        assert response.json()["is_active"] is False

    def test_create_duplicate_name_returns_409(
        self, client: TestClient, seeded_integration: AvailableIntegration
    ) -> None:
        response = client.post(
            "/admin/integrations/available",
            json={
                "name": "QuickBooks Online",
                "type": "erp",
            },
        )
        assert response.status_code == 409

    def test_create_validates_required_fields(self, client: TestClient) -> None:
        # Missing name
        response = client.post(
            "/admin/integrations/available",
            json={"type": "erp"},
        )
        assert response.status_code == 422

        # Missing type
        response = client.post(
            "/admin/integrations/available",
            json={"name": "Test"},
        )
        assert response.status_code == 422

    def test_create_validates_field_length(self, client: TestClient) -> None:
        # Empty name
        response = client.post(
            "/admin/integrations/available",
            json={"name": "", "type": "erp"},
        )
        assert response.status_code == 422

    def test_create_with_oauth_config(self, client: TestClient) -> None:
        response = client.post(
            "/admin/integrations/available",
            json={
                "name": "Xero",
                "type": "erp",
                "oauth_config": {
                    "authorization_url": "https://login.xero.com/authorize",
                    "token_url": "https://identity.xero.com/connect/token",
                    "scopes": ["openid", "accounting.transactions"],
                },
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["oauth_config"]["authorization_url"] == "https://login.xero.com/authorize"
        assert data["oauth_config"]["scopes"] == ["openid", "accounting.transactions"]

    def test_create_defaults(self, client: TestClient) -> None:
        response = client.post(
            "/admin/integrations/available",
            json={"name": "Minimal", "type": "erp"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["description"] is None
        assert data["supported_entities"] == []
        assert data["is_active"] is True
        assert data["oauth_config"] is None


# =============================================================================
# GET /admin/integrations/available — List
# =============================================================================


class TestListAvailableIntegrations:
    def test_list_all_includes_inactive(
        self, client: TestClient, mock_repo: MockIntegrationRepository
    ) -> None:
        mock_repo.seed_available_integration(name="Active", is_active=True)
        mock_repo.seed_available_integration(name="Inactive", is_active=False)

        response = client.get("/admin/integrations/available")
        assert response.status_code == 200
        data = response.json()
        assert len(data["integrations"]) == 2

    def test_list_with_include_inactive_false(
        self, client: TestClient, mock_repo: MockIntegrationRepository
    ) -> None:
        mock_repo.seed_available_integration(name="Active", is_active=True)
        mock_repo.seed_available_integration(name="Inactive", is_active=False)

        response = client.get("/admin/integrations/available?include_inactive=false")
        assert response.status_code == 200
        data = response.json()
        assert len(data["integrations"]) == 1
        assert data["integrations"][0]["name"] == "Active"

    def test_list_empty(self, client: TestClient) -> None:
        response = client.get("/admin/integrations/available")
        assert response.status_code == 200
        assert response.json()["integrations"] == []


# =============================================================================
# GET /admin/integrations/available/{id} — Get by ID
# =============================================================================


class TestGetAvailableIntegration:
    def test_get_success(
        self, client: TestClient, seeded_integration: AvailableIntegration
    ) -> None:
        response = client.get(f"/admin/integrations/available/{seeded_integration.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "QuickBooks Online"
        assert data["id"] == str(seeded_integration.id)

    def test_get_inactive_integration(
        self, client: TestClient, mock_repo: MockIntegrationRepository
    ) -> None:
        inactive = mock_repo.seed_available_integration(name="Inactive", is_active=False)
        response = client.get(f"/admin/integrations/available/{inactive.id}")
        assert response.status_code == 200
        assert response.json()["is_active"] is False

    def test_get_not_found(self, client: TestClient) -> None:
        response = client.get(f"/admin/integrations/available/{uuid4()}")
        assert response.status_code == 404


# =============================================================================
# PUT /admin/integrations/available/{id} — Update
# =============================================================================


class TestUpdateAvailableIntegration:
    def test_partial_update_single_field(
        self, client: TestClient, seeded_integration: AvailableIntegration
    ) -> None:
        response = client.put(
            f"/admin/integrations/available/{seeded_integration.id}",
            json={"description": "Updated description"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["description"] == "Updated description"
        # Other fields unchanged
        assert data["name"] == "QuickBooks Online"
        assert data["type"] == "erp"

    def test_full_update(
        self, client: TestClient, seeded_integration: AvailableIntegration
    ) -> None:
        response = client.put(
            f"/admin/integrations/available/{seeded_integration.id}",
            json={
                "name": "QBO Renamed",
                "type": "accounting",
                "description": "New desc",
                "supported_entities": ["vendor", "bill", "invoice"],
                "is_active": False,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "QBO Renamed"
        assert data["type"] == "accounting"
        assert data["description"] == "New desc"
        assert data["supported_entities"] == ["vendor", "bill", "invoice"]
        assert data["is_active"] is False

    def test_soft_delete(
        self, client: TestClient, seeded_integration: AvailableIntegration
    ) -> None:
        response = client.put(
            f"/admin/integrations/available/{seeded_integration.id}",
            json={"is_active": False},
        )
        assert response.status_code == 200
        assert response.json()["is_active"] is False

    def test_update_not_found(self, client: TestClient) -> None:
        response = client.put(
            f"/admin/integrations/available/{uuid4()}",
            json={"name": "Doesn't matter"},
        )
        assert response.status_code == 404

    def test_update_name_conflict(
        self,
        client: TestClient,
        mock_repo: MockIntegrationRepository,
        seeded_integration: AvailableIntegration,
    ) -> None:
        mock_repo.seed_available_integration(name="Xero", type="erp")

        response = client.put(
            f"/admin/integrations/available/{seeded_integration.id}",
            json={"name": "Xero"},
        )
        assert response.status_code == 409

    def test_update_same_name_no_conflict(
        self, client: TestClient, seeded_integration: AvailableIntegration
    ) -> None:
        # Updating with the same name should not conflict
        response = client.put(
            f"/admin/integrations/available/{seeded_integration.id}",
            json={"name": "QuickBooks Online", "description": "Updated"},
        )
        assert response.status_code == 200


# =============================================================================
# Soft-delete visibility: hidden from user endpoint, visible from admin
# =============================================================================


class TestSoftDeleteVisibility:
    def test_soft_deleted_hidden_from_active_only(
        self, mock_repo: MockIntegrationRepository
    ) -> None:
        """Soft-deleted integrations should not appear when active_only=True."""
        import asyncio

        mock_repo.seed_available_integration(name="Active", is_active=True)
        mock_repo.seed_available_integration(name="Inactive", is_active=False)

        # active_only=True (user endpoint behavior)
        active = asyncio.get_event_loop().run_until_complete(
            mock_repo.get_available_integrations(active_only=True)
        )
        assert len(active) == 1
        assert active[0].name == "Active"

        # active_only=False (admin endpoint behavior)
        all_integrations = asyncio.get_event_loop().run_until_complete(
            mock_repo.get_available_integrations(active_only=False)
        )
        assert len(all_integrations) == 2

    def test_admin_list_shows_inactive_after_soft_delete(
        self,
        client: TestClient,
        seeded_integration: AvailableIntegration,
    ) -> None:
        # Soft delete
        client.put(
            f"/admin/integrations/available/{seeded_integration.id}",
            json={"is_active": False},
        )

        # Admin list still shows it
        response = client.get("/admin/integrations/available")
        assert response.status_code == 200
        integrations = response.json()["integrations"]
        assert len(integrations) == 1
        assert integrations[0]["is_active"] is False

    def test_admin_get_shows_inactive(
        self,
        client: TestClient,
        seeded_integration: AvailableIntegration,
    ) -> None:
        # Soft delete
        client.put(
            f"/admin/integrations/available/{seeded_integration.id}",
            json={"is_active": False},
        )

        # Admin get still shows it
        response = client.get(f"/admin/integrations/available/{seeded_integration.id}")
        assert response.status_code == 200
        assert response.json()["is_active"] is False
