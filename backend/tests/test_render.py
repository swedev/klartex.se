"""Render endpoint — requires xelatex to be on PATH."""

import shutil

import pytest
from fastapi.testclient import TestClient

from klartex_se.main import app

client = TestClient(app)

XELATEX = shutil.which("xelatex")
needs_xelatex = pytest.mark.skipif(XELATEX is None, reason="xelatex not on PATH")


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
    r = client.post("/render", json=body)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"


def test_render_validation_error_returns_structured_400():
    body = {
        "template": "_block",
        "data": {"body": [{"type": "heading"}]},  # missing required `text`
    }
    r = client.post("/render", json=body)
    assert r.status_code == 400
    detail = r.json()["detail"]
    # klartex.render() wraps both unknown-template and schema-validation
    # failures as ValueError → input_error. The message carries the detail.
    assert detail["type"] == "input_error"
    assert "text" in detail["message"]  # mentions the missing field


def test_render_unknown_template_returns_400():
    r = client.post("/render", json={"template": "nope", "data": {}})
    assert r.status_code == 400
    assert r.json()["detail"]["type"] == "input_error"
