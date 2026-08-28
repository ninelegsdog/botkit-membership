"""Shared fixtures for botkit-membership tests."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

_PAYLOADS_DIR = Path(__file__).parent / "fixtures" / "payloads"


@pytest.fixture
def load_payload() -> Any:
    """Load a JSON Telegram-update fixture from tests/fixtures/payloads/."""

    def _load(name: str) -> dict[str, Any]:
        return json.loads((_PAYLOADS_DIR / name).read_text(encoding="utf-8"))  # type: ignore[no-any-return]

    return _load


def pytest_collection_modifyitems(config: Any, items: Any) -> None:
    """Tag offline tests as no_req; skip real Telegram (req) tests without RUN_TELEGRAM_E2E=1."""
    for item in items:
        if "req" in item.keywords:
            if os.getenv("RUN_TELEGRAM_E2E") != "1":
                item.add_marker(
                    pytest.mark.skip(reason="set RUN_TELEGRAM_E2E=1 to run real Telegram tests")
                )
        elif "no_req" not in item.keywords:
            item.add_marker(pytest.mark.no_req)
