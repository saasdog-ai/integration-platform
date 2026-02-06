"""Utility functions."""

import re


def sanitize_error_for_log(error: Exception) -> str:
    """Sanitize error message to remove potential credentials."""
    error_msg = str(error)
    # Remove potential tokens/secrets from error messages
    # Pattern matches common token formats
    sanitized = re.sub(
        r'(token|bearer|key|secret|password|credential|auth)["\s:=]+[^\s"\'&]{10,}',
        r"\1=[REDACTED]",
        error_msg,
        flags=re.IGNORECASE,
    )
    # Also redact long base64-like strings that could be tokens
    sanitized = re.sub(
        r"[A-Za-z0-9+/=]{40,}",
        "[REDACTED_TOKEN]",
        sanitized,
    )
    return sanitized
