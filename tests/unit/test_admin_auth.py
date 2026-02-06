"""Tests for admin API authentication."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.auth.admin import require_admin_api_key


@pytest.fixture
def mock_settings_dev_no_key():
    """Mock settings for development with no API key."""
    settings = MagicMock()
    settings.is_development = True
    settings.admin_api_key = None
    return settings


@pytest.fixture
def mock_settings_dev_with_key():
    """Mock settings for development with API key configured."""
    settings = MagicMock()
    settings.is_development = True
    settings.admin_api_key = "dev-test-key"
    return settings


@pytest.fixture
def mock_settings_prod_with_key():
    """Mock settings for production with API key configured."""
    settings = MagicMock()
    settings.is_development = False
    settings.admin_api_key = "prod-secret-key"
    return settings


@pytest.fixture
def mock_settings_prod_no_key():
    """Mock settings for production with no API key configured."""
    settings = MagicMock()
    settings.is_development = False
    settings.admin_api_key = None
    return settings


class TestAdminApiKeyAuthentication:
    """Tests for admin API key authentication."""

    @pytest.mark.asyncio
    async def test_dev_mode_bypass_when_no_key_configured(self, mock_settings_dev_no_key):
        """Test that dev mode allows access without API key when none configured."""
        with patch("app.auth.admin.get_settings", return_value=mock_settings_dev_no_key):
            # Should not raise - dev mode bypass
            result = await require_admin_api_key(api_key=None)
            assert result is None

    @pytest.mark.asyncio
    async def test_dev_mode_requires_key_when_configured(self, mock_settings_dev_with_key):
        """Test that dev mode requires key if one is configured."""
        with patch("app.auth.admin.get_settings", return_value=mock_settings_dev_with_key):
            # Should raise 401 without key
            with pytest.raises(HTTPException) as exc_info:
                await require_admin_api_key(api_key=None)
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_dev_mode_accepts_valid_key(self, mock_settings_dev_with_key):
        """Test that dev mode accepts valid API key."""
        with patch("app.auth.admin.get_settings", return_value=mock_settings_dev_with_key):
            result = await require_admin_api_key(api_key="dev-test-key")
            assert result is None

    @pytest.mark.asyncio
    async def test_dev_mode_rejects_invalid_key(self, mock_settings_dev_with_key):
        """Test that dev mode rejects invalid API key."""
        with patch("app.auth.admin.get_settings", return_value=mock_settings_dev_with_key):
            with pytest.raises(HTTPException) as exc_info:
                await require_admin_api_key(api_key="wrong-key")
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_prod_mode_returns_503_when_not_configured(self, mock_settings_prod_no_key):
        """Test that production mode returns 503 when API key not configured."""
        with patch("app.auth.admin.get_settings", return_value=mock_settings_prod_no_key):
            with pytest.raises(HTTPException) as exc_info:
                await require_admin_api_key(api_key=None)
            assert exc_info.value.status_code == 503
            assert "not configured" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_prod_mode_requires_valid_key(self, mock_settings_prod_with_key):
        """Test that production mode requires valid API key."""
        with patch("app.auth.admin.get_settings", return_value=mock_settings_prod_with_key):
            # Missing key
            with pytest.raises(HTTPException) as exc_info:
                await require_admin_api_key(api_key=None)
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_prod_mode_accepts_valid_key(self, mock_settings_prod_with_key):
        """Test that production mode accepts valid API key."""
        with patch("app.auth.admin.get_settings", return_value=mock_settings_prod_with_key):
            result = await require_admin_api_key(api_key="prod-secret-key")
            assert result is None

    @pytest.mark.asyncio
    async def test_prod_mode_rejects_wrong_key(self, mock_settings_prod_with_key):
        """Test that production mode rejects wrong API key."""
        with patch("app.auth.admin.get_settings", return_value=mock_settings_prod_with_key):
            with pytest.raises(HTTPException) as exc_info:
                await require_admin_api_key(api_key="wrong-key")
            assert exc_info.value.status_code == 401
            assert "Invalid or missing" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_empty_string_key_rejected(self, mock_settings_prod_with_key):
        """Test that empty string API key is rejected."""
        with patch("app.auth.admin.get_settings", return_value=mock_settings_prod_with_key):
            with pytest.raises(HTTPException) as exc_info:
                await require_admin_api_key(api_key="")
            assert exc_info.value.status_code == 401
