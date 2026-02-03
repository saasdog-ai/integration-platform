"""Tests for authentication modules."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from jose import jwt

from app.auth.jwt import JWTPayload, create_token, verify_token


@pytest.fixture
def mock_settings():
    """Create mock settings for JWT tests."""
    settings = MagicMock()
    settings.jwt_secret_key = "test-secret-key-for-testing-12345"
    settings.jwt_algorithm = "HS256"
    settings.jwt_issuer = "test-issuer"
    settings.jwt_audience = "test-audience"
    return settings


@pytest.fixture
def sample_client_id():
    """Sample client ID."""
    return uuid4()


class TestJWTPayload:
    """Tests for JWTPayload model."""

    def test_create_payload_with_all_fields(self):
        """Test creating payload with all fields."""
        client_id = uuid4()
        now = datetime.now(UTC)

        payload = JWTPayload(
            sub="user-123",
            client_id=client_id,
            exp=now + timedelta(hours=1),
            iat=now,
            iss="test-issuer",
            aud="test-audience",
            scopes=["read", "write"],
        )

        assert payload.sub == "user-123"
        assert payload.client_id == client_id
        assert payload.scopes == ["read", "write"]

    def test_create_payload_with_defaults(self):
        """Test creating payload with default values."""
        payload = JWTPayload()

        assert payload.sub is None
        assert payload.client_id is None
        assert payload.scopes == []


class TestCreateToken:
    """Tests for token creation."""

    def test_create_token_basic(self, mock_settings, sample_client_id):
        """Test creating a basic token."""
        with patch("app.auth.jwt.get_settings", return_value=mock_settings):
            token = create_token(sample_client_id)

        assert token is not None
        assert isinstance(token, str)

        # Decode without verification to check structure
        decoded = jwt.decode(
            token,
            mock_settings.jwt_secret_key,
            algorithms=[mock_settings.jwt_algorithm],
            options={"verify_aud": False},
        )
        assert decoded["client_id"] == str(sample_client_id)

    def test_create_token_with_user_id(self, mock_settings, sample_client_id):
        """Test creating a token with user ID."""
        with patch("app.auth.jwt.get_settings", return_value=mock_settings):
            token = create_token(sample_client_id, user_id="user-456")

        decoded = jwt.decode(
            token,
            mock_settings.jwt_secret_key,
            algorithms=[mock_settings.jwt_algorithm],
            options={"verify_aud": False},
        )
        assert decoded["sub"] == "user-456"

    def test_create_token_with_scopes(self, mock_settings, sample_client_id):
        """Test creating a token with scopes."""
        with patch("app.auth.jwt.get_settings", return_value=mock_settings):
            token = create_token(
                sample_client_id, scopes=["integrations:read", "integrations:write"]
            )

        decoded = jwt.decode(
            token,
            mock_settings.jwt_secret_key,
            algorithms=[mock_settings.jwt_algorithm],
            options={"verify_aud": False},
        )
        assert decoded["scopes"] == ["integrations:read", "integrations:write"]

    def test_create_token_expiration(self, mock_settings, sample_client_id):
        """Test token expiration is set correctly."""
        with patch("app.auth.jwt.get_settings", return_value=mock_settings):
            token = create_token(sample_client_id, expires_in_seconds=7200)

        decoded = jwt.decode(
            token,
            mock_settings.jwt_secret_key,
            algorithms=[mock_settings.jwt_algorithm],
            options={"verify_aud": False, "verify_exp": False},
        )
        assert "exp" in decoded
        assert "iat" in decoded


class TestVerifyToken:
    """Tests for token verification."""

    def test_verify_valid_token(self, mock_settings, sample_client_id):
        """Test verifying a valid token."""
        with patch("app.auth.jwt.get_settings", return_value=mock_settings):
            token = create_token(sample_client_id, user_id="user-789")
            payload = verify_token(token)

        assert payload.client_id == sample_client_id
        assert payload.sub == "user-789"

    def test_verify_token_expired(self, mock_settings, sample_client_id):
        """Test verifying an expired token."""
        with patch("app.auth.jwt.get_settings", return_value=mock_settings):
            # Create token that expires immediately
            token = create_token(sample_client_id, expires_in_seconds=-10)

            with pytest.raises(ValueError) as exc_info:
                verify_token(token)

            assert "expired" in str(exc_info.value).lower()

    def test_verify_token_invalid_signature(self, mock_settings, sample_client_id):
        """Test verifying token with invalid signature."""
        with patch("app.auth.jwt.get_settings", return_value=mock_settings):
            token = create_token(sample_client_id)

        # Modify settings to use different key
        mock_settings.jwt_secret_key = "different-key"

        with patch("app.auth.jwt.get_settings", return_value=mock_settings):
            with pytest.raises(ValueError) as exc_info:
                verify_token(token)

            assert "invalid" in str(exc_info.value).lower()

    def test_verify_token_missing_client_id(self, mock_settings):
        """Test verifying token without client_id claim."""
        now = datetime.now(UTC)
        payload = {
            "sub": "user-123",
            "exp": (now + timedelta(hours=1)).timestamp(),
            "iat": now.timestamp(),
            "iss": mock_settings.jwt_issuer,
            "aud": mock_settings.jwt_audience,
        }
        token = jwt.encode(
            payload,
            mock_settings.jwt_secret_key,
            algorithm=mock_settings.jwt_algorithm,
        )

        with patch("app.auth.jwt.get_settings", return_value=mock_settings):
            with pytest.raises(ValueError) as exc_info:
                verify_token(token)

            assert "client_id" in str(exc_info.value)

    def test_verify_token_invalid_client_id_format(self, mock_settings):
        """Test verifying token with invalid client_id format."""
        now = datetime.now(UTC)
        payload = {
            "client_id": "not-a-uuid",
            "exp": (now + timedelta(hours=1)).timestamp(),
            "iat": now.timestamp(),
            "iss": mock_settings.jwt_issuer,
            "aud": mock_settings.jwt_audience,
        }
        token = jwt.encode(
            payload,
            mock_settings.jwt_secret_key,
            algorithm=mock_settings.jwt_algorithm,
        )

        with patch("app.auth.jwt.get_settings", return_value=mock_settings):
            with pytest.raises(ValueError) as exc_info:
                verify_token(token)

            assert "invalid client_id format" in str(exc_info.value).lower()

    def test_verify_token_parses_times(self, mock_settings, sample_client_id):
        """Test that exp and iat are correctly parsed as datetime."""
        with patch("app.auth.jwt.get_settings", return_value=mock_settings):
            token = create_token(sample_client_id)
            payload = verify_token(token)

        assert payload.exp is not None
        assert isinstance(payload.exp, datetime)
        assert payload.iat is not None
        assert isinstance(payload.iat, datetime)

    def test_verify_token_parses_scopes(self, mock_settings, sample_client_id):
        """Test that scopes are correctly parsed."""
        with patch("app.auth.jwt.get_settings", return_value=mock_settings):
            token = create_token(sample_client_id, scopes=["read", "write", "admin"])
            payload = verify_token(token)

        assert payload.scopes == ["read", "write", "admin"]


class TestJWTIntegration:
    """Integration tests for JWT flow."""

    def test_create_and_verify_full_token(self, mock_settings, sample_client_id):
        """Test creating and verifying a token with all fields."""
        with patch("app.auth.jwt.get_settings", return_value=mock_settings):
            token = create_token(
                client_id=sample_client_id,
                user_id="user-integration-test",
                scopes=["integrations:*"],
                expires_in_seconds=3600,
            )

            payload = verify_token(token)

        assert payload.client_id == sample_client_id
        assert payload.sub == "user-integration-test"
        assert "integrations:*" in payload.scopes
        assert payload.exp > datetime.now(UTC)

    def test_token_roundtrip_preserves_data(self, mock_settings, sample_client_id):
        """Test that data survives a create/verify roundtrip."""
        original_scopes = ["scope1", "scope2", "scope3"]
        original_user = "roundtrip-user"

        with patch("app.auth.jwt.get_settings", return_value=mock_settings):
            token = create_token(
                client_id=sample_client_id,
                user_id=original_user,
                scopes=original_scopes,
            )

            payload = verify_token(token)

        assert payload.sub == original_user
        assert payload.scopes == original_scopes
        assert payload.client_id == sample_client_id
