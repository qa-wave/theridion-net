"""Tests for cookie jar persistence and manipulation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from theridion_sidecar.cookies import (
    CookieJar,
    StoredCookie,
    clear,
    from_httpx_response,
    load,
    save,
    to_httpx_cookies,
)


# Use a fixed UUID for all tests.
_ENV_ID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture(autouse=True)
def _set_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("THERIDION_HOME", str(tmp_path))


# ---------------------------------------------------------------------------
# load
# ---------------------------------------------------------------------------

def test_load_empty_jar() -> None:
    jar = load(_ENV_ID)
    assert jar.environment_id == _ENV_ID
    assert jar.cookies == []


def test_load_invalid_uuid_raises() -> None:
    with pytest.raises(ValueError):
        load("not-a-uuid")


# ---------------------------------------------------------------------------
# save + load round trip
# ---------------------------------------------------------------------------

def test_save_and_load_round_trip() -> None:
    jar = CookieJar(
        environment_id=_ENV_ID,
        cookies=[
            StoredCookie(name="session", value="abc123", domain="example.com"),
            StoredCookie(name="csrf", value="token456"),
        ],
    )
    save(jar)
    loaded = load(_ENV_ID)
    assert loaded.environment_id == _ENV_ID
    assert len(loaded.cookies) == 2
    assert loaded.cookies[0].name == "session"
    assert loaded.cookies[0].value == "abc123"
    assert loaded.cookies[1].name == "csrf"


def test_save_overwrites_previous() -> None:
    jar1 = CookieJar(
        environment_id=_ENV_ID,
        cookies=[StoredCookie(name="old", value="1")],
    )
    save(jar1)

    jar2 = CookieJar(
        environment_id=_ENV_ID,
        cookies=[StoredCookie(name="new", value="2")],
    )
    save(jar2)

    loaded = load(_ENV_ID)
    assert len(loaded.cookies) == 1
    assert loaded.cookies[0].name == "new"


# ---------------------------------------------------------------------------
# from_httpx_response
# ---------------------------------------------------------------------------

def test_from_httpx_response_merge_new() -> None:
    existing = CookieJar(
        environment_id=_ENV_ID,
        cookies=[StoredCookie(name="a", value="1")],
    )
    merged = from_httpx_response(_ENV_ID, existing, {"b": "2"})
    names = {c.name for c in merged.cookies}
    assert names == {"a", "b"}


def test_from_httpx_response_overwrites_existing() -> None:
    existing = CookieJar(
        environment_id=_ENV_ID,
        cookies=[StoredCookie(name="a", value="old")],
    )
    merged = from_httpx_response(_ENV_ID, existing, {"a": "new"})
    assert len(merged.cookies) == 1
    assert merged.cookies[0].value == "new"


def test_from_httpx_response_empty_response() -> None:
    existing = CookieJar(
        environment_id=_ENV_ID,
        cookies=[StoredCookie(name="keep", value="me")],
    )
    merged = from_httpx_response(_ENV_ID, existing, {})
    assert len(merged.cookies) == 1


# ---------------------------------------------------------------------------
# clear
# ---------------------------------------------------------------------------

def test_clear_existing() -> None:
    jar = CookieJar(
        environment_id=_ENV_ID,
        cookies=[StoredCookie(name="x", value="y")],
    )
    save(jar)
    assert clear(_ENV_ID) is True
    # After clear, loading returns empty.
    assert load(_ENV_ID).cookies == []


def test_clear_nonexistent() -> None:
    assert clear(_ENV_ID) is False


# ---------------------------------------------------------------------------
# to_httpx_cookies
# ---------------------------------------------------------------------------

def test_to_httpx_cookies_flat_dict() -> None:
    jar = CookieJar(
        environment_id=_ENV_ID,
        cookies=[
            StoredCookie(name="a", value="1"),
            StoredCookie(name="b", value="2"),
        ],
    )
    result = to_httpx_cookies(jar)
    assert result == {"a": "1", "b": "2"}


def test_to_httpx_cookies_empty() -> None:
    jar = CookieJar(environment_id=_ENV_ID)
    assert to_httpx_cookies(jar) == {}
