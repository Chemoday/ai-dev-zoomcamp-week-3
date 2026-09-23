"""Fixtures for integration tests that talk HTTP to a real running relay.

Nothing here imports the application: the tests exercise whatever API (and
therefore whatever database) is listening at ``RELAY_BASE_URL`` — a local
uvicorn, the Docker container, the Compose stack, or a kind port-forward.

If ``RELAY_BASE_URL`` is set explicitly, an unreachable API is a test failure
(CI must not silently skip).  Otherwise the default local URL is tried and the
tests are skipped when nothing is listening, so a bare ``pytest`` still works.
"""

from __future__ import annotations

import os

import httpx
import pytest

DEFAULT_BASE_URL = "http://127.0.0.1:8000"


@pytest.fixture(scope="session")
def base_url() -> str:
    explicit = os.getenv("RELAY_BASE_URL")
    url = (explicit or DEFAULT_BASE_URL).rstrip("/")
    try:
        ready = httpx.get(f"{url}/ready", timeout=5)
    except httpx.HTTPError as exc:
        if explicit:
            pytest.fail(f"Agent Relay API at {url} is unreachable: {exc}")
        pytest.skip(f"no Agent Relay API at {url}; set RELAY_BASE_URL to run integration tests")
    assert ready.status_code == 200, f"{url}/ready returned {ready.status_code}: {ready.text}"
    return url


@pytest.fixture
def client(base_url: str):
    with httpx.Client(base_url=f"{base_url}/api/v1", timeout=40) as http:
        yield http
