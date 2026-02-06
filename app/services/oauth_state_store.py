"""In-memory OAuth state store with TTL for CSRF prevention."""

import secrets
import time
from dataclasses import dataclass
from threading import Lock
from uuid import UUID


@dataclass
class OAuthStateEntry:
    """Stored OAuth state data."""

    client_id: UUID
    integration_id: UUID
    redirect_uri: str
    created_at: float
    expires_at: float


class OAuthStateStore:
    """Thread-safe in-memory store for OAuth state tokens."""

    def __init__(self, ttl_seconds: int = 600) -> None:  # 10 minutes default
        self._store: dict[str, OAuthStateEntry] = {}
        self._lock = Lock()
        self._ttl = ttl_seconds

    def create_state(
        self,
        client_id: UUID,
        integration_id: UUID,
        redirect_uri: str,
    ) -> str:
        """Generate and store a new state token."""
        state = secrets.token_urlsafe(32)
        now = time.time()

        with self._lock:
            # Cleanup expired entries opportunistically
            self._cleanup_expired()

            self._store[state] = OAuthStateEntry(
                client_id=client_id,
                integration_id=integration_id,
                redirect_uri=redirect_uri,
                created_at=now,
                expires_at=now + self._ttl,
            )

        return state

    def validate_and_consume(
        self,
        state: str,
        client_id: UUID,
    ) -> OAuthStateEntry | None:
        """Validate state and remove it (one-time use). Returns entry if valid."""
        with self._lock:
            entry = self._store.pop(state, None)

            if entry is None:
                return None

            # Check expiration
            if time.time() > entry.expires_at:
                return None

            # Check client_id matches
            if entry.client_id != client_id:
                return None

            return entry

    def _cleanup_expired(self) -> None:
        """Remove expired entries. Called within lock."""
        now = time.time()
        expired = [k for k, v in self._store.items() if now > v.expires_at]
        for k in expired:
            del self._store[k]


# Singleton instance
_oauth_state_store: OAuthStateStore | None = None


def get_oauth_state_store() -> OAuthStateStore:
    """Get the singleton OAuth state store."""
    global _oauth_state_store
    if _oauth_state_store is None:
        _oauth_state_store = OAuthStateStore()
    return _oauth_state_store
