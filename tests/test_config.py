"""Tests for config.py: Settings defaults and validate_settings."""

from __future__ import annotations

from copy import deepcopy

import pytest

from matyan_frontier.config import SETTINGS, Settings, validate_settings


class TestSettingsDefaults:
    def test_port(self) -> None:
        assert Settings().port == 53801

    def test_host(self) -> None:
        assert Settings().host == "0.0.0.0"

    def test_log_level(self) -> None:
        assert Settings().log_level == "INFO"

    def test_kafka_topic(self) -> None:
        assert Settings().kafka_data_ingestion_topic == "data-ingestion"

    def test_s3_bucket(self) -> None:
        assert Settings().s3_bucket == "matyan-artifacts"

    def test_s3_presign_expiry(self) -> None:
        assert Settings().s3_presign_expiry == 3600

    def test_metrics_enabled(self) -> None:
        assert Settings().metrics_enabled is True

    def test_s3_public_endpoint_empty_by_default(self) -> None:
        assert Settings().s3_public_endpoint == ""

    def test_shutdown_flush_timeout(self) -> None:
        assert Settings().shutdown_flush_timeout == 5.0

    def test_kafka_security_empty_by_default(self) -> None:
        s = Settings()
        assert s.kafka_security_protocol == ""
        assert s.kafka_sasl_mechanism == ""
        assert s.kafka_sasl_username == ""
        assert s.kafka_sasl_password == ""


def _settings(**overrides: object) -> Settings:
    """Build a Settings copy with overrides applied."""
    data = deepcopy(SETTINGS.model_dump())
    data.update(overrides)
    return Settings(**data)


class TestValidateSettings:
    def test_defaults_pass(self) -> None:
        validate_settings(SETTINGS)

    def test_multiple_bootstrap_servers(self) -> None:
        validate_settings(_settings(kafka_bootstrap_servers="host1:9092,host2:9093"))

    # -- kafka_bootstrap_servers errors --

    def test_empty_bootstrap_servers(self) -> None:
        with pytest.raises(ValueError, match="kafka_bootstrap_servers must not be empty"):
            validate_settings(_settings(kafka_bootstrap_servers=""))

    def test_bootstrap_no_colon(self) -> None:
        with pytest.raises(ValueError, match="must be host:port"):
            validate_settings(_settings(kafka_bootstrap_servers="localhost"))

    def test_bootstrap_empty_segment(self) -> None:
        with pytest.raises(ValueError, match="empty segment"):
            validate_settings(_settings(kafka_bootstrap_servers="host1:9092,,host2:9093"))

    def test_bootstrap_non_numeric_port(self) -> None:
        with pytest.raises(ValueError, match="not a valid integer"):
            validate_settings(_settings(kafka_bootstrap_servers="host:abc"))

    def test_bootstrap_port_zero(self) -> None:
        with pytest.raises(ValueError, match="out of range"):
            validate_settings(_settings(kafka_bootstrap_servers="host:0"))

    def test_bootstrap_port_too_large(self) -> None:
        with pytest.raises(ValueError, match="out of range"):
            validate_settings(_settings(kafka_bootstrap_servers="host:99999"))

    # -- s3_endpoint errors --

    def test_empty_s3_endpoint(self) -> None:
        with pytest.raises(ValueError, match="s3_endpoint must not be empty"):
            validate_settings(_settings(s3_endpoint=""))

    def test_s3_endpoint_bad_scheme(self) -> None:
        with pytest.raises(ValueError, match="http or https"):
            validate_settings(_settings(s3_endpoint="ftp://host"))

    def test_s3_endpoint_no_host(self) -> None:
        with pytest.raises(ValueError, match="missing a host"):
            validate_settings(_settings(s3_endpoint="http://"))

    # -- s3_public_endpoint errors --

    def test_s3_public_endpoint_bad_scheme(self) -> None:
        with pytest.raises(ValueError, match=r"s3_public_endpoint.*http or https"):
            validate_settings(_settings(s3_public_endpoint="ftp://host"))

    def test_s3_public_endpoint_empty_is_ok(self) -> None:
        validate_settings(_settings(s3_public_endpoint=""))

    def test_s3_public_endpoint_valid(self) -> None:
        validate_settings(_settings(s3_public_endpoint="https://s3.example.com"))

    # -- s3_bucket errors --

    def test_empty_s3_bucket(self) -> None:
        with pytest.raises(ValueError, match="s3_bucket must not be empty"):
            validate_settings(_settings(s3_bucket=""))

    def test_whitespace_only_s3_bucket(self) -> None:
        with pytest.raises(ValueError, match="s3_bucket must not be empty"):
            validate_settings(_settings(s3_bucket="   "))
