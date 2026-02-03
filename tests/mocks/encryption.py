"""Mock encryption service for testing."""

import base64
from typing import ClassVar

from app.core.exceptions import EncryptionError
from app.domain.interfaces import EncryptionServiceInterface


class MockEncryptionService(EncryptionServiceInterface):
    """
    Mock encryption service for testing.

    This implementation uses simple base64 encoding (NOT actual encryption)
    to allow tests to verify encrypted data without real crypto operations.
    """

    KEY_ID: ClassVar[str] = "mock-test-key"

    def __init__(self) -> None:
        self.encrypt_calls: list[bytes] = []
        self.decrypt_calls: list[tuple[bytes, str]] = []
        self.should_fail_encrypt = False
        self.should_fail_decrypt = False

    async def encrypt(self, plaintext: bytes) -> tuple[bytes, str]:
        """Mock encrypt - just base64 encode."""
        self.encrypt_calls.append(plaintext)

        if self.should_fail_encrypt:
            raise EncryptionError("Mock encryption failure")

        # Simple base64 "encryption" for testing
        ciphertext = base64.b64encode(plaintext)
        return ciphertext, self.KEY_ID

    async def decrypt(self, ciphertext: bytes, key_id: str) -> bytes:
        """Mock decrypt - just base64 decode."""
        self.decrypt_calls.append((ciphertext, key_id))

        if self.should_fail_decrypt:
            raise Exception("Mock decryption failure")

        if key_id != self.KEY_ID:
            raise Exception(f"Unknown key ID: {key_id}")

        # Simple base64 "decryption" for testing
        plaintext = base64.b64decode(ciphertext)
        return plaintext

    def reset(self) -> None:
        """Reset tracked calls and state."""
        self.encrypt_calls.clear()
        self.decrypt_calls.clear()
        self.should_fail_encrypt = False
        self.should_fail_decrypt = False
