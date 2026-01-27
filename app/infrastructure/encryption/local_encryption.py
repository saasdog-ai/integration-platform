"""Local encryption for development and testing (NOT for production)."""

import base64
import hashlib
import os
import secrets
from typing import ClassVar

from cryptography.fernet import Fernet

from app.core.config import get_settings
from app.core.exceptions import EncryptionError
from app.core.logging import get_logger
from app.domain.interfaces import EncryptionServiceInterface

logger = get_logger(__name__)


class LocalEncryptionService(EncryptionServiceInterface):
    """
    Local encryption service using Fernet symmetric encryption.

    WARNING: This is for development/testing only. NOT suitable for production.
    In production, use AWS KMS, Azure Key Vault, or GCP KMS.
    """

    KEY_ID: ClassVar[str] = "local-dev-key"

    def __init__(self, secret_key: str | None = None) -> None:
        """
        Initialize local encryption service.

        Args:
            secret_key: Optional secret key. If not provided, derives from JWT secret.
        """
        settings = get_settings()

        if secret_key:
            key_bytes = secret_key.encode()
        else:
            # Derive key from JWT secret (for consistency in dev)
            key_bytes = settings.jwt_secret_key.encode()

        # Create a Fernet key from the secret (must be 32 bytes, base64 encoded)
        key_hash = hashlib.sha256(key_bytes).digest()
        fernet_key = base64.urlsafe_b64encode(key_hash)
        self._fernet = Fernet(fernet_key)

        if settings.is_production:
            logger.warning(
                "LocalEncryptionService should NOT be used in production. "
                "Configure AWS KMS, Azure Key Vault, or GCP KMS."
            )

    async def encrypt(self, plaintext: bytes) -> tuple[bytes, str]:
        """
        Encrypt data using Fernet.

        Returns:
            Tuple of (ciphertext, key_id)
        """
        try:
            ciphertext = self._fernet.encrypt(plaintext)
            return ciphertext, self.KEY_ID
        except Exception as e:
            logger.error("Encryption failed", extra={"error": str(e)})
            raise EncryptionError(f"Encryption failed: {e}")

    async def decrypt(self, ciphertext: bytes, key_id: str) -> bytes:
        """
        Decrypt data using Fernet.

        Args:
            ciphertext: The encrypted data
            key_id: The key ID (must match KEY_ID)

        Returns:
            The decrypted plaintext
        """
        if key_id != self.KEY_ID:
            raise EncryptionError(f"Unknown key ID: {key_id}")

        try:
            plaintext = self._fernet.decrypt(ciphertext)
            return plaintext
        except Exception as e:
            logger.error("Decryption failed", extra={"error": str(e)})
            raise EncryptionError(f"Decryption failed: {e}")
