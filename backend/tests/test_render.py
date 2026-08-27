"""Render endpoint — requires xelatex to be on PATH for actual renders."""

import base64
import shutil
import threading

import pytest
from fastapi.testclient import TestClient

from klartex_se import render as render_module
from klartex_se.main import app

client = TestClient(app)

XELATEX = shutil.which("xelatex")
needs_xelatex = pytest.mark.skipif(XELATEX is None, reason="xelatex not on PATH")


def b64(s: str | bytes) -> str:
    if isinstance(s, str):
        s = s.encode()
    return base64.b64encode(s).decode()


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


def test_render_block_error_message_carries_body_index():
    """Block validation errors point at the offending block as `body[i]`.

    klartex wraps block validation as ValueError, so the position reaches
    clients only inside `detail.message` — there is no structured `path`
    for this case. The assertion pins that the index survives the
    passthrough in render.py.
    """
    body = {
        "template": "_block",
        "data": {
            "body": [
                {"type": "heading", "text": "ok"},
                {"type": "text"},  # missing required `text`
            ]
        },
    }
    r = client.post("/render", json=body)
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["type"] == "input_error"
    assert "body[1]" in detail["message"]
    assert "path" not in detail

    body["data"]["body"] = [{"type": "text"}]
    r = client.post("/render", json=body)
    assert r.status_code == 400
    assert "body[0]" in r.json()["detail"]["message"]


def test_render_unknown_template_returns_400():
    r = client.post("/render", json={"template": "nope", "data": {}})
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
    )
    assert r.status_code in (200, 500)
    if r.status_code == 400:
        # If we ever get here, the built-in passthrough broke.
        assert r.json()["detail"]["type"] != "unknown_page_template"


# --- Concurrency cap -------------------------------------------------------
#
# The tests below never invoke xelatex: klartex_render is replaced by a fake,
# so they exercise the semaphore alone and run anywhere.

MINIMAL_BODY = {
    "template": "_block",
    "data": {"body": [{"type": "heading", "text": "x"}]},
}


@pytest.fixture
def render_slots(monkeypatch):
    """Give each test its own semaphore, so a failure cannot leak slots."""
    slots = threading.BoundedSemaphore(render_module.MAX_CONCURRENT_RENDERS)
    monkeypatch.setattr(render_module, "_render_slots", slots)
    return slots


def assert_all_slots_free(slots):
    """Every slot is free — and no more than MAX_CONCURRENT_RENDERS exist."""
    acquired = [
        slots.acquire(blocking=False)
        for _ in range(render_module.MAX_CONCURRENT_RENDERS)
    ]
    extra = slots.acquire(blocking=False)
    for ok in acquired:
        if ok:
            slots.release()
    if extra:
        slots.release()
    assert all(acquired), "a render slot leaked"
    assert not extra, "more slots than MAX_CONCURRENT_RENDERS"


def test_render_returns_503_when_all_slots_taken(render_slots):
    for _ in range(render_module.MAX_CONCURRENT_RENDERS):
        assert render_slots.acquire(blocking=False)

    r = client.post("/render", json=MINIMAL_BODY)

    assert r.status_code == 503
    assert r.headers["Retry-After"] == "5"
    assert r.json()["detail"]["type"] == "overloaded"


def test_render_releases_slot_after_success(render_slots, monkeypatch):
    monkeypatch.setattr(
        render_module, "klartex_render", lambda *a, **kw: b"%PDF-fake"
    )

    r = client.post("/render", json=MINIMAL_BODY)

    assert r.status_code == 200
    assert_all_slots_free(render_slots)


def test_render_releases_slot_after_failure(render_slots, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("xelatex exploded")

    monkeypatch.setattr(render_module, "klartex_render", boom)

    r = client.post("/render", json=MINIMAL_BODY)

    assert r.status_code == 500
    assert r.json()["detail"]["type"] == "render_error"
    assert_all_slots_free(render_slots)


def test_render_third_concurrent_request_gets_503(render_slots, monkeypatch):
    """Two renders occupy both slots; a third is rejected immediately."""
    in_render = threading.Semaphore(0)
    release = threading.Event()

    def blocking_render(*args, **kwargs):
        in_render.release()
        assert release.wait(timeout=10), "render fake was never released"
        return b"%PDF-fake"

    monkeypatch.setattr(render_module, "klartex_render", blocking_render)

    results: dict[int, int] = {}

    def run(index):
        results[index] = client.post("/render", json=MINIMAL_BODY).status_code

    threads = [
        threading.Thread(target=run, args=(i, ), daemon=True)
        for i in range(render_module.MAX_CONCURRENT_RENDERS)
    ]
    for t in threads:
        t.start()
    try:
        for _ in threads:
            assert in_render.acquire(timeout=10), "renders never started"

        r = client.post("/render", json=MINIMAL_BODY)
        assert r.status_code == 503
        assert r.json()["detail"]["type"] == "overloaded"
    finally:
        release.set()
        for t in threads:
            t.join(timeout=10)

    assert not any(t.is_alive() for t in threads)
    assert sorted(results.values()) == [200] * len(threads)
    assert_all_slots_free(render_slots)
