from __future__ import annotations

from urllib.parse import urlparse

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_MIN_PORT = 1
_MAX_PORT = 65535

# Dev defaults used only for production guard checks.
_DEV_S3_CRED = "rustfsadmin"
_DEV_S3_ENDPOINT = "http://localhost:9000"
_DEV_KAFKA_BOOTSTRAP = "localhost:9092"


def validate_production_settings(settings: Settings) -> None:
    """When environment is production, require that S3/Kafka settings are not dev defaults."""
    if settings.environment != "production":
        return
    if settings.s3_access_key == _DEV_S3_CRED:
        msg = "In production, S3_ACCESS_KEY must be set explicitly (not dev default). Set from env or secrets backend."
        raise ValueError(msg)
    if settings.s3_secret_key == _DEV_S3_CRED:
        msg = "In production, S3_SECRET_KEY must be set explicitly (not dev default). Set from env or secrets backend."
        raise ValueError(msg)
    if settings.s3_endpoint == _DEV_S3_ENDPOINT:
        msg = "In production, S3_ENDPOINT must be set explicitly (not dev default). Set from env."
        raise ValueError(msg)
    if not settings.s3_endpoint.strip():
        msg = "In production, S3_ENDPOINT must be set (non-empty)."
        raise ValueError(msg)
    if settings.kafka_bootstrap_servers == _DEV_KAFKA_BOOTSTRAP:
        msg = "In production, KAFKA_BOOTSTRAP_SERVERS must be set explicitly (not dev default). Set from env."
        raise ValueError(msg)
    if not settings.kafka_bootstrap_servers.strip():
        msg = "In production, KAFKA_BOOTSTRAP_SERVERS must be set (non-empty)."
        raise ValueError(msg)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = Field(
        default="development",
        validation_alias=AliasChoices("MATYAN_ENVIRONMENT", "ENVIRONMENT"),
    )

    log_level: str = "INFO"

    port: int = 53801
    host: str = "0.0.0.0"

    # Kafka
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_data_ingestion_topic: str = "data-ingestion"
    kafka_security_protocol: str = ""
    kafka_sasl_mechanism: str = ""
    kafka_sasl_username: str = ""
    kafka_sasl_password: str = ""

    # S3 (RustFS in dev, AWS S3 in prod)
    s3_endpoint: str = "http://localhost:9000"
    s3_public_endpoint: str = ""
    s3_access_key: str = "rustfsadmin"
    s3_secret_key: str = "rustfsadmin"  # noqa: S105
    s3_bucket: str = "matyan-artifacts"
    s3_region: str = "us-east-1"
    s3_presign_expiry: int = 3600

    # Shutdown
    shutdown_flush_timeout: float = 5.0

    # Prometheus metrics
    metrics_enabled: bool = True

    # CORS
    cors_origins: tuple[str, ...] = (
        "http://localhost:3000",
        "http://localhost:8000",
        "http://localhost:53800",
        "http://127.0.0.1:53800",
    )


def _validate_bootstrap_servers(value: str) -> None:
    """Raise ``ValueError`` if *value* is not a valid ``host:port[,host:port...]`` list."""
    if not value.strip():
        msg = "kafka_bootstrap_servers must not be empty"
        raise ValueError(msg)
    for segment in value.split(","):
        segment = segment.strip()  # noqa: PLW2901
        if not segment:
            msg = "kafka_bootstrap_servers contains an empty segment"
            raise ValueError(msg)
        if ":" not in segment:
            msg = f"kafka_bootstrap_servers segment {segment!r} must be host:port"
            raise ValueError(msg)
        port_str = segment.rsplit(":", 1)[1]
        try:
            port = int(port_str)
        except ValueError:
            msg = f"kafka_bootstrap_servers port {port_str!r} is not a valid integer"
            raise ValueError(msg) from None
        if port < _MIN_PORT or port > _MAX_PORT:
            msg = f"kafka_bootstrap_servers port {port} is out of range ({_MIN_PORT}-{_MAX_PORT})"
            raise ValueError(msg)


def _validate_s3_url(value: str, field: str) -> None:
    """Raise ``ValueError`` if *value* is not a valid ``http(s)`` URL."""
    if not value.strip():
        msg = f"{field} must not be empty"
        raise ValueError(msg)
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https"):
        msg = f"{field} must use http or https scheme, got {parsed.scheme!r}"
        raise ValueError(msg)
    if not parsed.netloc:
        msg = f"{field} is missing a host"
        raise ValueError(msg)


def validate_settings(settings: Settings) -> None:
    """Validate format of critical settings; raise ``ValueError`` on first failure."""
    _validate_bootstrap_servers(settings.kafka_bootstrap_servers)
    _validate_s3_url(settings.s3_endpoint, "s3_endpoint")
    if settings.s3_public_endpoint:
        _validate_s3_url(settings.s3_public_endpoint, "s3_public_endpoint")
    if not settings.s3_bucket.strip():
        msg = "s3_bucket must not be empty"
        raise ValueError(msg)


SETTINGS = Settings()
validate_production_settings(SETTINGS)
