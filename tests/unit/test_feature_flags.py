"""Tests for feature flag service."""

from app.core.config import Settings
from app.infrastructure.feature_flags import ConfigFeatureFlagService
from tests.mocks.feature_flags import MockFeatureFlagService


class TestConfigFeatureFlagService:
    """Tests for the Settings-backed feature flag service."""

    def test_reads_sync_globally_disabled(self):
        settings = Settings(sync_globally_disabled=True)
        svc = ConfigFeatureFlagService(settings)
        assert svc.is_sync_globally_disabled() is True

    def test_reads_sync_globally_enabled(self):
        settings = Settings(sync_globally_disabled=False)
        svc = ConfigFeatureFlagService(settings)
        assert svc.is_sync_globally_disabled() is False

    def test_is_integration_disabled_matching(self):
        settings = Settings(disabled_integrations=["QuickBooks Online", "Xero"])
        svc = ConfigFeatureFlagService(settings)
        assert svc.is_integration_disabled("QuickBooks Online") is True

    def test_is_integration_disabled_non_matching(self):
        settings = Settings(disabled_integrations=["Xero"])
        svc = ConfigFeatureFlagService(settings)
        assert svc.is_integration_disabled("QuickBooks Online") is False

    def test_get_disabled_integrations(self):
        settings = Settings(disabled_integrations=["Xero", "NetSuite"])
        svc = ConfigFeatureFlagService(settings)
        assert svc.get_disabled_integrations() == ["Xero", "NetSuite"]

    def test_is_job_termination_enabled(self):
        settings = Settings(job_termination_enabled=True)
        svc = ConfigFeatureFlagService(settings)
        assert svc.is_job_termination_enabled() is True

    def test_is_auth_enabled(self):
        settings = Settings(auth_enabled=False)
        svc = ConfigFeatureFlagService(settings)
        assert svc.is_auth_enabled() is False

    def test_is_rate_limit_enabled(self):
        settings = Settings(rate_limit_enabled=True)
        svc = ConfigFeatureFlagService(settings)
        assert svc.is_rate_limit_enabled() is True

    def test_is_job_runner_enabled(self):
        settings = Settings(job_runner_enabled=False)
        svc = ConfigFeatureFlagService(settings)
        assert svc.is_job_runner_enabled() is False

    def test_is_scheduler_enabled(self):
        settings = Settings(scheduler_enabled=True)
        svc = ConfigFeatureFlagService(settings)
        assert svc.is_scheduler_enabled() is True


class TestMockFeatureFlagService:
    """Tests for the mock feature flag service."""

    def test_defaults(self):
        mock = MockFeatureFlagService()
        assert mock.is_sync_globally_disabled() is False
        assert mock.is_integration_disabled("anything") is False
        assert mock.get_disabled_integrations() == []
        assert mock.is_job_termination_enabled() is True
        assert mock.is_auth_enabled() is False
        assert mock.is_rate_limit_enabled() is False
        assert mock.is_job_runner_enabled() is True
        assert mock.is_scheduler_enabled() is True

    def test_settable(self):
        mock = MockFeatureFlagService()
        mock.sync_globally_disabled = True
        mock.disabled_integrations = ["QuickBooks Online"]
        mock.job_termination_enabled = False
        mock.auth_enabled = True

        assert mock.is_sync_globally_disabled() is True
        assert mock.is_integration_disabled("QuickBooks Online") is True
        assert mock.is_integration_disabled("Xero") is False
        assert mock.is_job_termination_enabled() is False
        assert mock.is_auth_enabled() is True

    def test_reset(self):
        mock = MockFeatureFlagService()
        mock.sync_globally_disabled = True
        mock.disabled_integrations = ["Xero"]
        mock.reset()

        assert mock.is_sync_globally_disabled() is False
        assert mock.get_disabled_integrations() == []
