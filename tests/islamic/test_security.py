"""Tests for startup security-posture validation."""

import pytest

from freqtrade.exceptions import ConfigurationError
from freqtrade.islamic import validate_security_config


def test_dry_run_needs_no_credentials(default_conf) -> None:
    default_conf["dry_run"] = True
    default_conf["exchange"]["key"] = ""
    default_conf["exchange"]["secret"] = ""
    validate_security_config(default_conf)  # must not raise


def test_live_requires_credentials(default_conf) -> None:
    default_conf["dry_run"] = False
    default_conf["exchange"]["key"] = ""
    default_conf["exchange"]["secret"] = ""
    with pytest.raises(ConfigurationError, match="requires exchange API key"):
        validate_security_config(default_conf)


def test_live_with_credentials_ok(default_conf) -> None:
    default_conf["dry_run"] = False
    default_conf["exchange"]["key"] = "abc"
    default_conf["exchange"]["secret"] = "def"
    default_conf["api_server"] = {"enabled": False}
    validate_security_config(default_conf)


def test_local_api_server_needs_no_hardening(default_conf) -> None:
    default_conf["api_server"] = {
        "enabled": True,
        "listen_ip_address": "127.0.0.1",
        "jwt_secret_key": "",
        "username": "",
        "password": "",
    }
    validate_security_config(default_conf)


def test_exposed_api_requires_strong_jwt(default_conf) -> None:
    default_conf["api_server"] = {
        "enabled": True,
        "listen_ip_address": "0.0.0.0",
        "jwt_secret_key": "short",
        "username": "u",
        "password": "a-strong-pass",
    }
    with pytest.raises(ConfigurationError, match="jwt_secret_key"):
        validate_security_config(default_conf)


def test_exposed_api_requires_strong_password(default_conf) -> None:
    default_conf["api_server"] = {
        "enabled": True,
        "listen_ip_address": "0.0.0.0",
        "jwt_secret_key": "a" * 20,
        "username": "admin",
        "password": "admin",
    }
    with pytest.raises(ConfigurationError, match="username and a strong password"):
        validate_security_config(default_conf)


def test_exposed_api_fully_hardened_ok(default_conf) -> None:
    default_conf["api_server"] = {
        "enabled": True,
        "listen_ip_address": "0.0.0.0",
        "jwt_secret_key": "a" * 20,
        "username": "operator",
        "password": "a-strong-unique-password",
    }
    validate_security_config(default_conf)


def test_worker_aborts_on_exposed_insecure_api(default_conf, mocker) -> None:
    from freqtrade.worker import Worker

    default_conf["api_server"] = {
        "enabled": True,
        "listen_ip_address": "0.0.0.0",
        "jwt_secret_key": "short",
        "username": "u",
        "password": "p",
    }
    mocker.patch("freqtrade.configuration.Configuration.get_config", return_value=default_conf)
    with pytest.raises(ConfigurationError, match="Security"):
        Worker(args=None, config=None)
