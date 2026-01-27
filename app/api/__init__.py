"""API routers."""

from app.api.health import router as health_router
from app.api.integrations import router as integrations_router
from app.api.settings import router as settings_router
from app.api.sync_jobs import router as sync_jobs_router

__all__ = [
    "health_router",
    "integrations_router",
    "settings_router",
    "sync_jobs_router",
]
