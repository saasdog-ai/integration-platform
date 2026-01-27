"""Unit tests for encryption infrastructure."""

import pytest

from app.infrastructure.encryption.local_encryption import LocalEncryptionService
from tests.mocks.encryption import MockEncryptionService


class TestLocalEncryptionService:
    """Tests for LocalEncryptionService."""

    @pytest.fixture
    def service(self) -> LocalEncryptionService:
        """Create local encryption service."""
        return LocalEncryptionService(secret_key="test-secret-key")

    @pytest.mark.asyncio
    async def test_encrypt_decrypt_roundtrip(self, service: LocalEncryptionService):
        """Test that encrypt and decrypt are inverse operations."""
        plaintext = b"Hello, World! This is a test message."

        ciphertext, key_id = await service.encrypt(plaintext)
        assert ciphertext != plaintext
        assert key_id == LocalEncryptionService.KEY_ID

        decrypted = await service.decrypt(ciphertext, key_id)
        assert decrypted == plaintext

    @pytest.mark.asyncio
    async def test_decrypt_with_wrong_key_id_fails(
        self, service: LocalEncryptionService
    ):
        """Test that decryption fails with wrong key ID."""
        from app.core.exceptions import EncryptionError

        plaintext = b"Test data"
        ciphertext, _ = await service.encrypt(plaintext)

        with pytest.raises(EncryptionError):
            await service.decrypt(ciphertext, "wrong-key-id")

    @pytest.mark.asyncio
    async def test_encrypt_different_inputs_different_outputs(
        self, service: LocalEncryptionService
    ):
        """Test that different inputs produce different outputs."""
        plaintext1 = b"Message 1"
        plaintext2 = b"Message 2"

        ciphertext1, _ = await service.encrypt(plaintext1)
        ciphertext2, _ = await service.encrypt(plaintext2)

        assert ciphertext1 != ciphertext2


class TestMockEncryptionService:
    """Tests for MockEncryptionService."""

    @pytest.fixture
    def service(self) -> MockEncryptionService:
        """Create mock encryption service."""
        service = MockEncryptionService()
        yield service
        service.reset()

    @pytest.mark.asyncio
    async def test_encrypt_decrypt_roundtrip(self, service: MockEncryptionService):
        """Test mock encrypt/decrypt."""
        plaintext = b"Test data"

        ciphertext, key_id = await service.encrypt(plaintext)
        decrypted = await service.decrypt(ciphertext, key_id)

        assert decrypted == plaintext

    @pytest.mark.asyncio
    async def test_tracks_encrypt_calls(self, service: MockEncryptionService):
        """Test that encrypt calls are tracked."""
        await service.encrypt(b"Data 1")
        await service.encrypt(b"Data 2")

        assert len(service.encrypt_calls) == 2
        assert service.encrypt_calls[0] == b"Data 1"
        assert service.encrypt_calls[1] == b"Data 2"

    @pytest.mark.asyncio
    async def test_tracks_decrypt_calls(self, service: MockEncryptionService):
        """Test that decrypt calls are tracked."""
        ciphertext, key_id = await service.encrypt(b"Test")
        await service.decrypt(ciphertext, key_id)

        assert len(service.decrypt_calls) == 1

    @pytest.mark.asyncio
    async def test_configurable_failure(self, service: MockEncryptionService):
        """Test configurable failure mode."""
        service.should_fail_encrypt = True

        with pytest.raises(Exception):
            await service.encrypt(b"Test")

    @pytest.mark.asyncio
    async def test_reset_clears_state(self, service: MockEncryptionService):
        """Test that reset clears all state."""
        await service.encrypt(b"Test")
        service.should_fail_decrypt = True

        service.reset()

        assert len(service.encrypt_calls) == 0
        assert service.should_fail_decrypt is False
