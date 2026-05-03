"""Test fixtures. Mocks Gemini and provides Flask test client."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("GOOGLE_AI_API_KEY", "test-key-fixture")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

import app as app_module  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    """Clear the per-IP rate-limit bucket before each test.

    Tests run rapid-fire from the same fake IP; without this the limiter would
    kick in mid-suite and fail unrelated tests with 429.
    """
    app_module._RATE_LIMIT.clear()
    yield


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as c:
        yield c


@pytest.fixture
def app_mod():
    return app_module
