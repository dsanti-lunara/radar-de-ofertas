from __future__ import annotations

from pathlib import Path

import pytest

from radar.domain.secrets import (
    SECRET_ACCESS_DENIED,
    SECRET_MASK,
    SECRET_UNAVAILABLE,
    ScopedSecrets,
    Secret,
    SecretAccessDeniedError,
    SecretScope,
    SecretsProvider,
    SecretUnavailableError,
)
from radar.infrastructure.logging import SecretRedactor
from radar.infrastructure.secrets import EnvironmentSecretsProvider, environment_variable_for

pytestmark = pytest.mark.unit


def _provider(
    env: dict[str, str],
    *,
    redactor: SecretRedactor | None = None,
    references: dict[str, str] | None = None,
) -> EnvironmentSecretsProvider:
    return EnvironmentSecretsProvider(env=env, redactor=redactor, references=references or {})


def test_secret_repr_and_str_are_masked() -> None:
    secret = Secret(name="telegram_bot_token", _value="fake-secret")
    assert "fake-secret" not in repr(secret)
    assert "fake-secret" not in str(secret)
    assert SECRET_MASK in repr(secret)
    assert secret.reveal() == "fake-secret"


def test_provider_satisfies_protocol_and_returns_none_when_absent() -> None:
    provider = _provider({})
    assert isinstance(provider, SecretsProvider)
    assert provider.get("telegram_bot_token") is None


def test_provider_reads_value_and_registers_redaction() -> None:
    redactor = SecretRedactor()
    provider = _provider({"RADAR_SECRET_TELEGRAM_BOT_TOKEN": "fake-secret"}, redactor=redactor)
    secret = provider.get("telegram_bot_token")
    assert secret is not None
    assert secret.reveal() == "fake-secret"
    assert "fake-secret" not in redactor.redact("token=fake-secret")


def test_provider_honors_explicit_reference() -> None:
    provider = _provider({"MY_TOKEN": "v"}, references={"telegram_bot_token": "MY_TOKEN"})
    secret = provider.get("telegram_bot_token")
    assert secret is not None
    assert secret.reveal() == "v"


def test_environment_variable_name_mapping() -> None:
    assert environment_variable_for("telegram-bot.token") == "RADAR_SECRET_TELEGRAM_BOT_TOKEN"


def test_scoped_require_missing_blocks_capability() -> None:
    scoped = ScopedSecrets(
        provider=_provider({}),
        scope=SecretScope("telegram_publisher", frozenset({"telegram_bot_token"})),
    )
    with pytest.raises(SecretUnavailableError) as excinfo:
        scoped.require("telegram_bot_token")
    error = excinfo.value.error
    assert error.code == SECRET_UNAVAILABLE
    assert error.retryable is False
    assert error.action
    assert error.context == {"secret": "telegram_bot_token", "component": "telegram_publisher"}


def test_scoped_access_outside_allowlist_fails_closed() -> None:
    provider = _provider({"RADAR_SECRET_OTHER": "present-value"})
    scoped = ScopedSecrets(
        provider=provider,
        scope=SecretScope("telegram_publisher", frozenset({"telegram_bot_token"})),
    )
    with pytest.raises(SecretAccessDeniedError) as excinfo:
        scoped.get("other")
    assert excinfo.value.error.code == SECRET_ACCESS_DENIED
    assert excinfo.value.error.retryable is False
    assert "present-value" not in str(excinfo.value)


def test_provider_has_no_persistence_side_effects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    env = {"RADAR_SECRET_TELEGRAM_BOT_TOKEN": "fake-secret"}
    provider = _provider(env)
    secret = provider.get("telegram_bot_token")
    assert secret is not None
    assert list(tmp_path.iterdir()) == []
    assert env == {"RADAR_SECRET_TELEGRAM_BOT_TOKEN": "fake-secret"}
