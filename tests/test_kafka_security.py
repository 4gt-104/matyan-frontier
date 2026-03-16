"""Tests for kafka/_security.py: kafka_security_kwargs branches."""

from __future__ import annotations

from unittest.mock import patch

from matyan_frontier.kafka._security import kafka_security_kwargs


class TestKafkaSecurityKwargs:
    def test_all_empty(self) -> None:
        with patch("matyan_frontier.kafka._security.SETTINGS") as s:
            s.kafka_security_protocol = ""
            s.kafka_sasl_mechanism = ""
            s.kafka_sasl_username = ""
            s.kafka_sasl_password = ""
            assert kafka_security_kwargs() == {}

    def test_protocol_only(self) -> None:
        with patch("matyan_frontier.kafka._security.SETTINGS") as s:
            s.kafka_security_protocol = "SASL_SSL"
            s.kafka_sasl_mechanism = ""
            s.kafka_sasl_username = ""
            s.kafka_sasl_password = ""
            result = kafka_security_kwargs()
            assert result == {"security_protocol": "SASL_SSL"}

    def test_sasl_mechanism_only(self) -> None:
        with patch("matyan_frontier.kafka._security.SETTINGS") as s:
            s.kafka_security_protocol = ""
            s.kafka_sasl_mechanism = "PLAIN"
            s.kafka_sasl_username = ""
            s.kafka_sasl_password = ""
            result = kafka_security_kwargs()
            assert result == {"sasl_mechanism": "PLAIN"}

    def test_username_without_password(self) -> None:
        with patch("matyan_frontier.kafka._security.SETTINGS") as s:
            s.kafka_security_protocol = ""
            s.kafka_sasl_mechanism = ""
            s.kafka_sasl_username = "user"
            s.kafka_sasl_password = ""
            result = kafka_security_kwargs()
            assert result == {}

    def test_all_set(self) -> None:
        with patch("matyan_frontier.kafka._security.SETTINGS") as s:
            s.kafka_security_protocol = "SASL_SSL"
            s.kafka_sasl_mechanism = "PLAIN"
            s.kafka_sasl_username = "user"
            s.kafka_sasl_password = "pass"  # noqa: S105
            result = kafka_security_kwargs()
            assert result == {
                "security_protocol": "SASL_SSL",
                "sasl_mechanism": "PLAIN",
                "sasl_plain_username": "user",
                "sasl_plain_password": "pass",
            }
