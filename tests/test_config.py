from __future__ import annotations

import pytest

from qbrix._config import QbrixConfig


@pytest.mark.unit
class TestQbrixConfig:
    def test_defaults(self) -> None:
        cfg = QbrixConfig(api_key="optiq_test")
        assert cfg.base_url == "http://localhost:8080"
        assert cfg.timeout == 5.0
        assert cfg.max_retries == 0
        assert 429 in cfg.retry_on
        assert cfg.retry_base_delay == 0.5
        assert cfg.retry_max_delay == 30.0

    def test_constructor_overrides(self) -> None:
        cfg = QbrixConfig(
            api_key="optiq_xxx",
            base_url="https://api.qbrix.io",
            timeout=10.0,
            max_retries=5,
        )
        assert cfg.api_key == "optiq_xxx"
        assert cfg.base_url == "https://api.qbrix.io"
        assert cfg.timeout == 10.0
        assert cfg.max_retries == 5

    def test_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("QBRIX_API_KEY", "optiq_from_env")
        monkeypatch.setenv("QBRIX_BASE_URL", "https://env.qbrix.io")
        cfg = QbrixConfig()
        assert cfg.api_key == "optiq_from_env"
        assert cfg.base_url == "https://env.qbrix.io"

    def test_api_key_optional(self) -> None:
        cfg = QbrixConfig()
        assert cfg.api_key is None
