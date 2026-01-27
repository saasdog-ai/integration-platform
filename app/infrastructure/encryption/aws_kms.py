"""AWS KMS encryption service."""

from app.core.config import get_settings
from app.core.exceptions import EncryptionError
from app.core.logging import get_logger
from app.domain.interfaces import EncryptionServiceInterface

logger = get_logger(__name__)


class AWSKMSEncryptionService(EncryptionServiceInterface):
    """AWS KMS encryption service for production use."""

    def __init__(
        self,
        key_id: str | None = None,
        region: str | None = None,
        endpoint_url: str | None = None,
    ) -> None:
        """
        Initialize AWS KMS encryption service.

        Args:
            key_id: KMS key ID or ARN. If not provided, uses settings.
            region: AWS region. If not provided, uses settings.
            endpoint_url: Custom endpoint URL (for localstack).
        """
        settings = get_settings()
        self._key_id = key_id or settings.kms_key_id
        self._region = region or settings.aws_region
        self._endpoint_url = endpoint_url or settings.aws_endpoint_url
        self._client = None

        if not self._key_id:
            raise EncryptionError("KMS key ID not configured")

    def _get_client(self):
        """Lazily create KMS client."""
        if self._client is None:
            try:
                import boto3

                settings = get_settings()
                session_kwargs = {}
                if settings.aws_access_key_id:
                    session_kwargs["aws_access_key_id"] = settings.aws_access_key_id
                if settings.aws_secret_access_key:
                    session_kwargs["aws_secret_access_key"] = settings.aws_secret_access_key

                client_kwargs = {"region_name": self._region}
                if self._endpoint_url:
                    client_kwargs["endpoint_url"] = self._endpoint_url

                session = boto3.Session(**session_kwargs)
                self._client = session.client("kms", **client_kwargs)
            except ImportError:
                raise EncryptionError(
                    "boto3 is required for AWS KMS. Install with: pip install boto3"
                )

        return self._client

    async def encrypt(self, plaintext: bytes) -> tuple[bytes, str]:
        """
        Encrypt data using AWS KMS.

        Returns:
            Tuple of (ciphertext, key_id)
        """
        try:
            import asyncio

            client = self._get_client()
            loop = asyncio.get_event_loop()

            response = await loop.run_in_executor(
                None,
                lambda: client.encrypt(
                    KeyId=self._key_id,
                    Plaintext=plaintext,
                ),
            )

            ciphertext = response["CiphertextBlob"]
            key_id = response["KeyId"]

            logger.debug(
                "Data encrypted with KMS",
                extra={"key_id": key_id, "size": len(plaintext)},
            )

            return ciphertext, key_id

        except Exception as e:
            logger.error("KMS encryption failed", extra={"error": str(e)})
            raise EncryptionError(f"KMS encryption failed: {e}")

    async def decrypt(self, ciphertext: bytes, key_id: str) -> bytes:
        """
        Decrypt data using AWS KMS.

        Args:
            ciphertext: The encrypted data
            key_id: The key ID used for encryption

        Returns:
            The decrypted plaintext
        """
        try:
            import asyncio

            client = self._get_client()
            loop = asyncio.get_event_loop()

            response = await loop.run_in_executor(
                None,
                lambda: client.decrypt(
                    CiphertextBlob=ciphertext,
                    KeyId=key_id,
                ),
            )

            plaintext = response["Plaintext"]

            logger.debug(
                "Data decrypted with KMS",
                extra={"key_id": key_id, "size": len(plaintext)},
            )

            return plaintext

        except Exception as e:
            logger.error("KMS decryption failed", extra={"error": str(e)})
            raise EncryptionError(f"KMS decryption failed: {e}")
