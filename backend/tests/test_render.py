"""Render endpoint — requires xelatex to be on PATH for actual renders."""

import base64
import shutil

import pytest
from fastapi.testclient import TestClient

from klartex_se.main import app

client = TestClient(app)

XELATEX = shutil.which("xelatex")
needs_xelatex = pytest.mark.skipif(XELATEX is None, reason="xelatex not on PATH")

API_TOKEN = "test-token-do-not-use-in-prod"
AUTH = {"Authorization": f"Bearer {API_TOKEN}"}


@pytest.fixture(autouse=True)
def configured_token(monkeypatch):
    """All /render tests run with API_TOKEN set to the test value."""
    monkeypatch.setenv("API_TOKEN", API_TOKEN)
    yield


def b64(s: str | bytes) -> str:
    if isinstance(s, str):
        s = s.encode()
    return base64.b64encode(s).decode()


# --- Auth -------------------------------------------------------------------


def test_render_without_token_returns_401():
    r = client.post(
        "/render",
        json={"template": "_block", "data": {"body": []}},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "Missing Bearer token"


def test_render_with_bad_token_returns_401():
    r = client.post(
        "/render",
        json={"template": "_block", "data": {"body": []}},
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "Invalid Bearer token"


def test_render_with_unconfigured_token_returns_503(monkeypatch):
    monkeypatch.delenv("API_TOKEN", raising=False)
    r = client.post(
        "/render",
        json={"template": "_block", "data": {"body": []}},
        headers=AUTH,
    )
    assert r.status_code == 503


# --- Render -----------------------------------------------------------------


@needs_xelatex
def test_render_minimal_block_doc():
    body = {
        "template": "_block",
        "data": {
            "lang": "sv",
            "body": [
                {"type": "heading", "text": "Test"},
                {"type": "text", "text": "Hello world."},
            ],
        },
    }
    r = client.post("/render", json=body, headers=AUTH)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"


def test_render_validation_error_returns_structured_400():
    body = {
        "template": "_block",
        "data": {"body": [{"type": "heading"}]},  # missing required `text`
    }
    r = client.post("/render", json=body, headers=AUTH)
    assert r.status_code == 400
    detail = r.json()["detail"]
    # klartex.render() wraps both unknown-template and schema-validation
    # failures as ValueError → input_error. The message carries the detail.
    assert detail["type"] == "input_error"
    assert "text" in detail["message"]  # mentions the missing field


def test_render_unknown_template_returns_400():
    r = client.post(
        "/render",
        json={"template": "nope", "data": {}},
        headers=AUTH,
    )
    assert r.status_code == 400
    assert r.json()["detail"]["type"] == "input_error"


def test_render_unknown_page_template_returns_400(tmp_path, monkeypatch):
    monkeypatch.setenv("PAGE_TEMPLATES_DIR", str(tmp_path))
    r = client.post(
        "/render",
        json={
            "template": "_block",
            "data": {"body": [{"type": "heading", "text": "x"}]},
            "page_template": "never-registered",
        },
        headers=AUTH,
    )
    assert r.status_code == 400
    assert r.json()["detail"]["type"] == "unknown_page_template"


def test_render_builtin_page_template_passes_through(tmp_path, monkeypatch):
    """Built-in names (formal/clean/none) skip the bundle lookup."""
    monkeypatch.setenv("PAGE_TEMPLATES_DIR", str(tmp_path))
    # No bundle named "formal" exists; should NOT 400. With xelatex absent
    # we expect a render_error 500 (or success if xelatex present).
    r = client.post(
        "/render",
        json={
            "template": "_block",
            "data": {"body": [{"type": "heading", "text": "x"}]},
            "page_template": "formal",
        },
        headers=AUTH,
    )
    assert r.status_code in (200, 500)
    if r.status_code == 400:
        # If we ever get here, the built-in passthrough broke.
        assert r.json()["detail"]["type"] != "unknown_page_template"
