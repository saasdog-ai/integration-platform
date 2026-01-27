"""Integration adapters for external systems."""

from app.infrastructure.adapters.factory import (
    AdapterFactory,
    get_adapter_factory,
    reset_adapter_factory,
)

__all__ = [
    "AdapterFactory",
    "get_adapter_factory",
    "reset_adapter_factory",
]
