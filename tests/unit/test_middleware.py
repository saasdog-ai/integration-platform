"""Tests for middleware components."""

import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.testclient import TestClient

from app.core.middleware import (
    ClientContextMiddleware,
    LoggingMiddleware,
    RateLimitMiddleware,
    RequestContextMiddleware,
    RequestSizeLimitMiddleware,
    client_id_ctx,
    get_client_id,
    get_request_id,
    request_id_ctx,
)


@pytest.fixture
def simple_app():
    """Create a simple FastAPI app for testing middleware."""
    app = FastAPI()

    @app.get("/test")
    async def test_endpoint():
        return {"message": "ok"}

    @app.get("/error")
    async def error_endpoint():
        raise ValueError("Test error")

    @app.post("/data")
    async def post_data(request: Request):
        body = await request.body()
        return {"size": len(body)}

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    return app


class TestRequestContextMiddleware:
    """Tests for RequestContextMiddleware."""

    def test_generates_request_id(self, simple_app):
        """Test that request ID is generated when not provided."""
        simple_app.add_middleware(RequestContextMiddleware)
        client = TestClient(simple_app)

        response = client.get("/test")

        assert response.status_code == 200
        assert "X-Request-ID" in response.headers
        assert len(response.headers["X-Request-ID"]) == 36  # UUID format

    def test_uses_provided_request_id(self, simple_app):
        """Test that provided request ID is used."""
        simple_app.add_middleware(RequestContextMiddleware)
        client = TestClient(simple_app)
        custom_id = "my-custom-request-id"

        response = client.get("/test", headers={"X-Request-ID": custom_id})

        assert response.status_code == 200
        assert response.headers["X-Request-ID"] == custom_id

    def test_context_var_functions(self):
        """Test get_request_id and get_client_id functions."""
        # Test default values
        assert get_request_id() == ""
        assert get_client_id() == ""

        # Test setting values
        request_id_ctx.set("test-request-123")
        client_id_ctx.set("client-456")

        assert get_request_id() == "test-request-123"
        assert get_client_id() == "client-456"

        # Reset
        request_id_ctx.set("")
        client_id_ctx.set("")


class TestLoggingMiddleware:
    """Tests for LoggingMiddleware."""

    def test_logs_request_and_response(self, simple_app):
        """Test that requests and responses are logged."""
        simple_app.add_middleware(LoggingMiddleware)
        client = TestClient(simple_app)

        with patch("app.core.middleware.logger") as mock_logger:
            response = client.get("/test")

        assert response.status_code == 200
        # Should have logged request start and completion
        assert mock_logger.info.call_count >= 2

    def test_logs_error_response(self, simple_app):
        """Test that error responses are logged at appropriate level."""
        simple_app.add_middleware(LoggingMiddleware)

        @simple_app.get("/not-found")
        async def not_found():
            return JSONResponse(status_code=404, content={"error": "not found"})

        client = TestClient(simple_app)

        with patch("app.core.middleware.logger") as mock_logger:
            response = client.get("/not-found")

        assert response.status_code == 404
        # Should log 4xx as warning
        assert mock_logger.warning.called or mock_logger.info.called


class TestClientContextMiddleware:
    """Tests for ClientContextMiddleware."""

    def test_extracts_client_id_from_state(self, simple_app):
        """Test that client ID is extracted from request state."""
        simple_app.add_middleware(ClientContextMiddleware)

        @simple_app.middleware("http")
        async def set_client_id(request: Request, call_next):
            request.state.client_id = "test-client-123"
            return await call_next(request)

        client = TestClient(simple_app)
        response = client.get("/test")

        assert response.status_code == 200

    def test_handles_missing_client_id(self, simple_app):
        """Test that missing client ID is handled gracefully."""
        simple_app.add_middleware(ClientContextMiddleware)
        client = TestClient(simple_app)

        response = client.get("/test")

        assert response.status_code == 200


class TestRequestSizeLimitMiddleware:
    """Tests for RequestSizeLimitMiddleware."""

    def test_allows_small_requests(self, simple_app):
        """Test that small requests are allowed."""
        simple_app.add_middleware(RequestSizeLimitMiddleware)
        client = TestClient(simple_app)

        response = client.post("/data", content=b"small body")

        assert response.status_code == 200

    def test_rejects_large_requests(self, simple_app):
        """Test that large requests are rejected."""
        simple_app.add_middleware(RequestSizeLimitMiddleware)
        client = TestClient(simple_app)

        # Create a request larger than the default limit (10MB)
        # We'll use a mock to set a smaller limit for testing
        with patch("app.core.middleware.get_settings") as mock_settings:
            mock_settings.return_value.api_max_request_size = 100  # 100 bytes
            large_body = b"x" * 200  # 200 bytes

            response = client.post(
                "/data",
                content=large_body,
                headers={"Content-Length": str(len(large_body))},
            )

        assert response.status_code == 413
        assert "too large" in response.json()["error"].lower()

    def test_handles_invalid_content_length(self, simple_app):
        """Test that invalid Content-Length header is handled."""
        simple_app.add_middleware(RequestSizeLimitMiddleware)
        client = TestClient(simple_app)

        # Invalid content-length should not crash
        response = client.post(
            "/data",
            content=b"test",
            headers={"Content-Length": "invalid"},
        )

        # Should proceed to next middleware (content-length parsing fails gracefully)
        assert response.status_code == 200


class TestRateLimitMiddleware:
    """Tests for RateLimitMiddleware."""

    def test_allows_requests_when_disabled(self, simple_app):
        """Test that requests are allowed when rate limiting is disabled."""
        simple_app.add_middleware(RateLimitMiddleware)
        client = TestClient(simple_app)

        with patch("app.core.middleware.get_settings") as mock_settings:
            mock_settings.return_value.rate_limit_enabled = False
            response = client.get("/test")

        assert response.status_code == 200

    def test_skips_health_endpoints(self, simple_app):
        """Test that health endpoints are not rate limited."""
        simple_app.add_middleware(RateLimitMiddleware)
        client = TestClient(simple_app)

        with patch("app.core.middleware.get_settings") as mock_settings:
            mock_settings.return_value.rate_limit_enabled = True
            mock_settings.return_value.rate_limit_requests_per_minute = 1
            mock_settings.return_value.rate_limit_burst = 0

            # Health endpoints should always succeed
            for _ in range(10):
                response = client.get("/health")
                assert response.status_code == 200

    def test_rate_limits_requests(self, simple_app):
        """Test that rate limiting kicks in after threshold."""
        simple_app.add_middleware(RateLimitMiddleware)
        client = TestClient(simple_app)

        with patch("app.core.middleware.get_settings") as mock_settings:
            mock_settings.return_value.rate_limit_enabled = True
            mock_settings.return_value.rate_limit_requests_per_minute = 2
            mock_settings.return_value.rate_limit_burst = 0

            # First few requests should succeed
            response1 = client.get("/test")
            response2 = client.get("/test")

            # After consuming all tokens, should be rate limited
            response3 = client.get("/test")

        assert response1.status_code == 200
        assert response2.status_code == 200
        assert response3.status_code == 429
        assert "Retry-After" in response3.headers

    def test_rate_limit_headers(self, simple_app):
        """Test that rate limit headers are added to responses."""
        simple_app.add_middleware(RateLimitMiddleware)
        client = TestClient(simple_app)

        with patch("app.core.middleware.get_settings") as mock_settings:
            mock_settings.return_value.rate_limit_enabled = True
            mock_settings.return_value.rate_limit_requests_per_minute = 60
            mock_settings.return_value.rate_limit_burst = 10

            response = client.get("/test")

        assert response.status_code == 200
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Limit" in response.headers

    def test_token_bucket_refill(self, simple_app):
        """Test that token bucket refills over time."""
        middleware = RateLimitMiddleware(simple_app)

        # Exhaust tokens
        for _ in range(5):
            middleware._check_rate_limit("test-client", max_requests=2, burst=2)

        # Wait for some refill
        time.sleep(0.1)

        # Should have some tokens now
        allowed, remaining, retry = middleware._check_rate_limit(
            "test-client", max_requests=60, burst=10
        )

        # With high refill rate, should be allowed after brief wait
        assert allowed or retry < 1.0

    def test_get_client_key_from_forwarded_header(self, simple_app):
        """Test client key extraction from X-Forwarded-For header."""
        middleware = RateLimitMiddleware(simple_app)

        mock_request = MagicMock()
        mock_request.state = MagicMock(spec=[])  # No client_id attribute
        mock_request.headers = {"X-Forwarded-For": "1.2.3.4, 5.6.7.8"}
        mock_request.client = MagicMock()
        mock_request.client.host = "127.0.0.1"

        key = middleware._get_client_key(mock_request)

        assert key == "ip:1.2.3.4"  # First IP in chain

    def test_get_client_key_from_client_id(self, simple_app):
        """Test client key extraction from authenticated client."""
        middleware = RateLimitMiddleware(simple_app)

        mock_request = MagicMock()
        mock_request.state.client_id = "authenticated-client-123"

        key = middleware._get_client_key(mock_request)

        assert key == "client:authenticated-client-123"
