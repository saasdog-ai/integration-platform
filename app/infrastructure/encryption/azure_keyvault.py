"""Azure Key Vault encryption service."""

from app.core.config import get_settings
from app.core.exceptions import EncryptionError
from app.core.logging import get_logger
from app.domain.interfaces import EncryptionServiceInterface

logger = get_logger(__name__)


class AzureKeyVaultEncryptionService(EncryptionServiceInterface):
    """Azure Key Vault encryption service for production use."""

    def __init__(
        self,
        vault_url: str | None = None,
        key_name: str = "integration-platform-key",
    ) -> None:
        """
        Initialize Azure Key Vault encryption service.

        Args:
            vault_url: Key Vault URL. If not provided, uses settings.
            key_name: Name of the key to use for encryption.
        """
        settings = get_settings()
        self._vault_url = vault_url or settings.azure_keyvault_url
        self._key_name = key_name
        self._client = None
        self._crypto_client = None

        if not self._vault_url:
            raise EncryptionError("Azure Key Vault URL not configured")

    def _get_clients(self):
        """Lazily create Key Vault clients."""
        if self._client is None:
            try:
                from azure.identity import DefaultAzureCredential
                from azure.keyvault.keys import KeyClient
                from azure.keyvault.keys.crypto import CryptographyClient

                credential = DefaultAzureCredential()
                self._client = KeyClient(
                    vault_url=self._vault_url, credential=credential
                )

                # Get or create the key
                try:
                    key = self._client.get_key(self._key_name)
                except Exception:
                    key = self._client.create_rsa_key(self._key_name, size=2048)

                self._crypto_client = CryptographyClient(key, credential=credential)

            except ImportError:
                raise EncryptionError(
                    "azure-identity and azure-keyvault-keys are required. "
                    "Install with: pip install azure-identity azure-keyvault-keys"
                )

        return self._client, self._crypto_client

    async def encrypt(self, plaintext: bytes) -> tuple[bytes, str]:
        """
        Encrypt data using Azure Key Vault.

        Returns:
            Tuple of (ciphertext, key_id)
        """
        try:
            import asyncio

            from azure.keyvault.keys.crypto import EncryptionAlgorithm

            _, crypto_client = self._get_clients()
            loop = asyncio.get_event_loop()

            result = await loop.run_in_executor(
                None,
                lambda: crypto_client.encrypt(
                    EncryptionAlgorithm.rsa_oaep_256, plaintext
                ),
            )

            ciphertext = result.ciphertext
            key_id = result.key_id

            logger.debug(
                "Data encrypted with Azure Key Vault",
                extra={"key_id": key_id, "size": len(plaintext)},
            )

            return ciphertext, key_id

        except Exception as e:
            logger.error("Azure Key Vault encryption failed", extra={"error": str(e)})
            raise EncryptionError(f"Azure Key Vault encryption failed: {e}")

    async def decrypt(self, ciphertext: bytes, key_id: str) -> bytes:
        """
        Decrypt data using Azure Key Vault.

        Args:
            ciphertext: The encrypted data
            key_id: The key ID used for encryption

        Returns:
            The decrypted plaintext
        """
        try:
            import asyncio

            from azure.keyvault.keys.crypto import EncryptionAlgorithm

            _, crypto_client = self._get_clients()
            loop = asyncio.get_event_loop()

            result = await loop.run_in_executor(
                None,
                lambda: crypto_client.decrypt(
                    EncryptionAlgorithm.rsa_oaep_256, ciphertext
                ),
            )

            plaintext = result.plaintext

            logger.debug(
                "Data decrypted with Azure Key Vault",
                extra={"key_id": key_id, "size": len(plaintext)},
            )

            return plaintext

        except Exception as e:
            logger.error("Azure Key Vault decryption failed", extra={"error": str(e)})
            raise EncryptionError(f"Azure Key Vault decryption failed: {e}")
