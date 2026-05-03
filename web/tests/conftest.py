"""Test fixtures. Mocks Gemini and provides Flask test client."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("GOOGLE_AI_API_KEY", "test-key-fixture")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

import app as app_module  # noqa: E402


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as c:
        yield c


@pytest.fixture
def app_mod():
    return app_module
