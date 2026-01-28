"""Tests for health check endpoints."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.health import router


@pytest.fixture
def app():
    """Create test FastAPI app with health router."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


class TestHealthCheck:
    """Tests for basic health check endpoint."""

    def test_health_check_returns_healthy(self, client):
        """Test basic health check returns healthy status."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert "timestamp" in data

    def test_health_check_version_format(self, client):
        """Test health check returns valid version."""
        response = client.get("/health")

        data = response.json()
        assert data["version"] == "0.1.0"

    def test_health_check_timestamp_format(self, client):
        """Test health check returns valid timestamp."""
        response = client.get("/health")

        data = response.json()
        # Should be ISO format timestamp
        timestamp = datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))
        assert timestamp is not None


class TestReadinessCheck:
    """Tests for readiness check endpoint."""

    def test_readiness_check_returns_response(self, client):
        """Test readiness check returns valid response structure."""
        # The readiness check will try to connect to actual services
        # which may fail in test environment, but the endpoint should
        # always return a valid response with the correct structure
        response = client.get("/health/ready")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "database" in data
        assert "queue" in data
        assert "encryption" in data
        # Status should be either 'healthy' or 'degraded'
        assert data["status"] in ("healthy", "degraded")

    def test_readiness_check_database_unhealthy(self, client):
        """Test readiness check when database is unhealthy."""
        with patch("app.infrastructure.db.database.get_engine") as mock_get_engine:
            mock_get_engine.side_effect = Exception("Database connection failed")

            response = client.get("/health/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert "unhealthy" in data["database"]

    def test_readiness_check_queue_unhealthy(self, client):
        """Test readiness check when queue is unhealthy."""
        # Mock healthy database
        mock_engine = MagicMock()

        with patch("app.infrastructure.db.database.get_engine", return_value=mock_engine):
            with patch("app.infrastructure.queue.factory.get_message_queue") as mock_queue:
                mock_queue.side_effect = Exception("Queue unavailable")

                response = client.get("/health/ready")

        assert response.status_code == 200
        data = response.json()
        # Queue should be unhealthy
        assert "unhealthy" in data["queue"]

    def test_readiness_check_encryption_unhealthy(self, client):
        """Test readiness check when encryption is unhealthy."""
        mock_engine = MagicMock()

        with patch("app.infrastructure.db.database.get_engine", return_value=mock_engine):
            with patch("app.infrastructure.queue.factory.get_message_queue", return_value=MagicMock()):
                with patch("app.infrastructure.encryption.factory.get_encryption_service") as mock_encryption:
                    mock_encryption.side_effect = Exception("Encryption unavailable")

                    response = client.get("/health/ready")

        assert response.status_code == 200
        data = response.json()
        assert "unhealthy" in data["encryption"]


class TestLivenessCheck:
    """Tests for liveness check endpoint."""

    def test_liveness_check_returns_alive(self, client):
        """Test liveness check returns alive status."""
        response = client.get("/health/live")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "alive"
