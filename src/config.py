"""Application configuration loaded from .env file."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Server
    host: str = "0.0.0.0"
    port: int = 10666

    # Auth — model (Socket.IO)
    model_api_key: str = ""

    # Auth — user (REST)
    user_api_key: str = ""

    # JWT
    secret_key: str = "change-me"
    token_expire_seconds: int = 86400  # 24h

    # Timeouts & limits
    request_timeout: int = 1800  # 30 min
    max_concurrent_requests: int = 10

    # HTTPS proxy
    proxy_port: int = 10667
    proxy_user: str = "proxy"
    proxy_password: str = ""
    proxy_allowed_domains: str = "*"  # comma-separated or *
    proxy_max_connections: int = 50

    # Logging
    log_level: str = "INFO"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def proxy_domain_list(self) -> list[str] | None:
        """Return list of allowed domains or None for allow-all."""
        if self.proxy_allowed_domains.strip() == "*":
            return None
        return [d.strip() for d in self.proxy_allowed_domains.split(",") if d.strip()]


settings = Settings()
