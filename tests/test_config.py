"""Tests for configuration loading."""

from __future__ import annotations

import os

from src.config import Settings


def test_default_values(monkeypatch):
    """Default settings should have expected values (clear test env vars)."""
    # Clear env vars that conftest sets so defaults take effect
    for key in ("REQUEST_TIMEOUT", "MAX_CONCURRENT_REQUESTS", "PROXY_MAX_CONNECTIONS",
                "BASE_MODEL", "PROXY_USER", "LOG_LEVEL", "PORT", "HOST"):
        monkeypatch.delenv(key, raising=False)

    s = Settings(
        model_api_key="k",
        user_api_key="u",
        proxy_password="p",
        _env_file=None,
    )
    assert s.port == 10666
    assert s.proxy_port == 10667
    assert s.request_timeout == 1800
    assert s.max_concurrent_requests == 10
    assert s.base_model == "llama3"


def test_env_override():
    """Environment variables should override defaults."""
    s = Settings(
        port=9999,
        base_model="gpt-custom",
        model_api_key="k",
        user_api_key="u",
        proxy_password="p",
        _env_file=None,
    )
    assert s.port == 9999
    assert s.base_model == "gpt-custom"


def test_proxy_domain_list_wildcard():
    """'*' should return None (allow all)."""
    s = Settings(
        proxy_allowed_domains="*",
        model_api_key="k",
        user_api_key="u",
        proxy_password="p",
        _env_file=None,
    )
    assert s.proxy_domain_list is None


def test_proxy_domain_list_specific():
    """Comma-separated list should be parsed."""
    s = Settings(
        proxy_allowed_domains="api.openai.com, google.com, example.org",
        model_api_key="k",
        user_api_key="u",
        proxy_password="p",
        _env_file=None,
    )
    assert s.proxy_domain_list == ["api.openai.com", "google.com", "example.org"]


def test_proxy_domain_list_empty():
    """Empty string should return empty list."""
    s = Settings(
        proxy_allowed_domains="",
        model_api_key="k",
        user_api_key="u",
        proxy_password="p",
        _env_file=None,
    )
    assert s.proxy_domain_list == []
