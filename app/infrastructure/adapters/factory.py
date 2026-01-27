"""Adapter factory for creating integration adapters."""

from app.core.logging import get_logger
from app.domain.entities import AvailableIntegration
from app.domain.interfaces import AdapterFactoryInterface, IntegrationAdapterInterface

logger = get_logger(__name__)

# Singleton instance
_factory_instance: "AdapterFactory | None" = None


class AdapterFactory(AdapterFactoryInterface):
    """Factory for creating integration adapters."""

    def __init__(self) -> None:
        # Registry of adapter classes by integration name
        self._adapters: dict[str, type[IntegrationAdapterInterface]] = {}

    def register(
        self, integration_name: str, adapter_class: type[IntegrationAdapterInterface]
    ) -> None:
        """Register an adapter class for an integration."""
        self._adapters[integration_name] = adapter_class
        logger.debug(f"Registered adapter for {integration_name}")

    def get_adapter(
        self,
        integration: AvailableIntegration,
        access_token: str,
        external_account_id: str | None = None,
    ) -> IntegrationAdapterInterface:
        """Get adapter for the given integration."""
        adapter_class = self._adapters.get(integration.name)

        if not adapter_class:
            # Fall back to mock adapter for development
            from app.infrastructure.adapters.mock.client import MockAdapter

            logger.warning(
                f"No adapter registered for {integration.name}, using mock adapter"
            )
            return MockAdapter(
                integration_name=integration.name,
                access_token=access_token,
                external_account_id=external_account_id,
            )

        return adapter_class(
            integration_name=integration.name,
            access_token=access_token,
            external_account_id=external_account_id,
        )


def get_adapter_factory() -> AdapterFactory:
    """Get the singleton adapter factory."""
    global _factory_instance

    if _factory_instance is None:
        _factory_instance = AdapterFactory()

        # Register available adapters
        # In a real implementation, you'd register actual adapters here:
        # from app.infrastructure.adapters.quickbooks.client import QuickBooksAdapter
        # _factory_instance.register("QuickBooks Online", QuickBooksAdapter)

    return _factory_instance


def reset_adapter_factory() -> None:
    """Reset the adapter factory (for testing)."""
    global _factory_instance
    _factory_instance = None
