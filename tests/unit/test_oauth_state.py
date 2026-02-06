"""Tests for OAuth state store (CSRF protection)."""

import time
from uuid import uuid4

import pytest

from app.services.oauth_state_store import OAuthStateStore, get_oauth_state_store


@pytest.fixture
def state_store():
    """Create a fresh state store for each test."""
    return OAuthStateStore(ttl_seconds=10)


@pytest.fixture
def sample_client_id():
    """Sample client ID."""
    return uuid4()


@pytest.fixture
def sample_integration_id():
    """Sample integration ID."""
    return uuid4()


class TestOAuthStateStore:
    """Tests for OAuthStateStore."""

    def test_create_state_returns_unique_tokens(self, state_store, sample_client_id):
        """Test that state creation returns unique tokens."""
        integration_id = uuid4()
        redirect_uri = "https://app.example.com/callback"

        state1 = state_store.create_state(sample_client_id, integration_id, redirect_uri)
        state2 = state_store.create_state(sample_client_id, integration_id, redirect_uri)
        state3 = state_store.create_state(sample_client_id, integration_id, redirect_uri)

        assert state1 != state2
        assert state2 != state3
        assert state1 != state3
        # Each state should be a reasonably long string
        assert len(state1) >= 32
        assert len(state2) >= 32

    def test_validate_and_consume_succeeds_with_correct_data(
        self, state_store, sample_client_id, sample_integration_id
    ):
        """Test that state validation succeeds with correct data."""
        redirect_uri = "https://app.example.com/callback"

        state = state_store.create_state(sample_client_id, sample_integration_id, redirect_uri)

        entry = state_store.validate_and_consume(state, sample_client_id)

        assert entry is not None
        assert entry.client_id == sample_client_id
        assert entry.integration_id == sample_integration_id
        assert entry.redirect_uri == redirect_uri

    def test_state_consumed_on_first_use(
        self, state_store, sample_client_id, sample_integration_id
    ):
        """Test that state is consumed on first use (one-time use)."""
        redirect_uri = "https://app.example.com/callback"

        state = state_store.create_state(sample_client_id, sample_integration_id, redirect_uri)

        # First validation should succeed
        entry1 = state_store.validate_and_consume(state, sample_client_id)
        assert entry1 is not None

        # Second validation with same state should fail (already consumed)
        entry2 = state_store.validate_and_consume(state, sample_client_id)
        assert entry2 is None

    def test_expired_state_rejected(self, sample_client_id, sample_integration_id):
        """Test that expired state is rejected."""
        # Create store with very short TTL
        short_ttl_store = OAuthStateStore(ttl_seconds=0)
        redirect_uri = "https://app.example.com/callback"

        state = short_ttl_store.create_state(sample_client_id, sample_integration_id, redirect_uri)

        # Wait a tiny bit to ensure expiration
        time.sleep(0.01)

        entry = short_ttl_store.validate_and_consume(state, sample_client_id)
        assert entry is None

    def test_wrong_client_id_rejected(self, state_store, sample_client_id, sample_integration_id):
        """Test that validation fails with wrong client_id."""
        redirect_uri = "https://app.example.com/callback"

        state = state_store.create_state(sample_client_id, sample_integration_id, redirect_uri)

        wrong_client_id = uuid4()
        entry = state_store.validate_and_consume(state, wrong_client_id)
        assert entry is None

    def test_invalid_state_returns_none(self, state_store, sample_client_id):
        """Test that invalid state returns None."""
        entry = state_store.validate_and_consume("invalid-state-token", sample_client_id)
        assert entry is None

    def test_cleanup_removes_expired_entries(self, sample_client_id, sample_integration_id):
        """Test that expired entries are cleaned up."""
        short_ttl_store = OAuthStateStore(ttl_seconds=0)
        redirect_uri = "https://app.example.com/callback"

        # Create some states that will immediately expire
        for _ in range(5):
            short_ttl_store.create_state(sample_client_id, sample_integration_id, redirect_uri)

        time.sleep(0.01)

        # Creating a new state should trigger cleanup
        short_ttl_store.create_state(sample_client_id, sample_integration_id, redirect_uri)

        # The expired entries should be cleaned up
        # We can verify this by checking the internal store size
        # (the new entry should be the only one, or at most 2 due to timing)
        assert len(short_ttl_store._store) <= 2

    def test_stores_all_required_fields(self, state_store, sample_client_id, sample_integration_id):
        """Test that all required fields are stored and retrievable."""
        redirect_uri = "https://app.example.com/callback"

        state = state_store.create_state(sample_client_id, sample_integration_id, redirect_uri)

        entry = state_store.validate_and_consume(state, sample_client_id)

        assert entry is not None
        assert entry.client_id == sample_client_id
        assert entry.integration_id == sample_integration_id
        assert entry.redirect_uri == redirect_uri
        assert entry.created_at > 0
        assert entry.expires_at > entry.created_at


class TestGetOAuthStateStore:
    """Tests for singleton accessor."""

    def test_returns_singleton_instance(self):
        """Test that get_oauth_state_store returns a singleton."""
        store1 = get_oauth_state_store()
        store2 = get_oauth_state_store()

        assert store1 is store2

    def test_singleton_is_usable(self):
        """Test that the singleton store works correctly."""
        store = get_oauth_state_store()
        client_id = uuid4()
        integration_id = uuid4()
        redirect_uri = "https://test.example.com/callback"

        state = store.create_state(client_id, integration_id, redirect_uri)
        assert state is not None
        assert len(state) >= 32

        # Clean up by consuming the state
        store.validate_and_consume(state, client_id)
