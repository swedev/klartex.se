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
    r = client.post("/api/render", json=body)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"


def post_block_error(body_blocks):
    """POST a block document expected to fail validation; return the detail."""
    r = client.post(
        "/api/render",
        json={"template": "_block", "data": {"body": body_blocks}},
    )
    assert r.status_code == 400, r.text
    return r.json()["detail"]


def test_render_validation_error_returns_structured_400():
    """Block validation errors carry both a message and a structured path.

    klartex.render() wraps block validation as ValueError → input_error;
    render.py recovers the block position from the message and reports it
    as `detail.path`, in the same list shape the jsonschema path uses.
    """
    detail = post_block_error([{"type": "heading"}])  # missing required `text`
    assert detail["type"] == "input_error"
    assert "text" in detail["message"]  # mentions the missing field
    assert detail["path"] == ["body", 0]


def test_render_block_error_path_points_at_the_offending_block():
    detail = post_block_error(
        [
            {"type": "heading", "text": "ok"},
            {"type": "text"},  # missing required `text`
        ]
    )
    assert detail["type"] == "input_error"
    assert detail["path"] == ["body", 1]
    assert "body[1]" in detail["message"]  # message stays readable


def test_render_block_error_path_reaches_into_the_block():
    """A field-level failure inside a block extends the path to the field."""
    detail = post_block_error([{"type": "heading", "text": 123}])
    assert detail["path"] == ["body", 0, "text"]

    detail = post_block_error([{"type": "list", "items": [{"text": 5}]}])
    assert detail["path"] == ["body", 0, "items", 0, "text"]


def test_render_block_error_path_covers_nested_blocks():
    """Blocks nested in a carrier block get their full position."""
    columns = [[{"type": "text", "text": "a"}], [{"type": "text"}]]
    detail = post_block_error([{"type": "columns", "items": columns}])
    assert detail["path"] == ["body", 0, "items", 1, 0]

    columns[1][0] = {"type": "text", "text": 123}  # wrong field type
    detail = post_block_error([{"type": "columns", "items": columns}])
    assert detail["path"] == ["body", 0, "items", 1, 0, "text"]


def test_render_unknown_block_type_carries_path():
    detail = post_block_error([{"type": "nope", "text": "x"}])
    assert detail["type"] == "input_error"
    assert detail["path"] == ["body", 0]


def test_render_unknown_block_type_cannot_forge_a_path():
    """A block type carrying its own `at body[...]` does not move the path."""
    forged = "x' at body[9]. Available: y"
    detail = post_block_error([{"type": forged, "text": "x"}])
    assert detail["path"] == ["body", 0]


def test_render_schema_validation_path_is_unchanged():
    """Both error paths report the same shape for the same position."""
    detail = post_block_error([{"text": "x"}])  # block without `type`
    assert detail["type"] == "validation_error"
    assert detail["path"] == ["body", 0]

    r = client.post("/api/render", json={"template": "_block", "data": {}})
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["type"] == "validation_error"
    assert detail["path"] == []


def test_block_error_path_handles_unreachable_missing_type_form():
    """The `Block at ... is missing 'type'` form the API cannot reach today."""
    exc = ValueError("Block at body[2].content[0] is missing 'type'")
    assert render_module._block_error_path(exc) == ["body", 2, "content", 0]


def test_block_error_path_returns_none_for_other_errors():
    assert render_module._block_error_path(ValueError("Unknown template")) is None


def test_render_unknown_template_returns_400():
    """An error with no block position carries no `path`."""
    r = client.post("/api/render", json={"template": "nope", "data": {}})
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["type"] == "input_error"
    assert "path" not in detail


def test_render_unknown_page_template_returns_400(tmp_path, monkeypatch):
    monkeypatch.setenv("PAGE_TEMPLATES_DIR", str(tmp_path))
    r = client.post(
        "/api/render",
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
        "/api/render",
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

    r = client.post("/api/render", json=MINIMAL_BODY)

    assert r.status_code == 503
    assert r.headers["Retry-After"] == "5"
    assert r.json()["detail"]["type"] == "overloaded"


def test_render_releases_slot_after_success(render_slots, monkeypatch):
    monkeypatch.setattr(
        render_module, "klartex_render", lambda *a, **kw: b"%PDF-fake"
    )

    r = client.post("/api/render", json=MINIMAL_BODY)

    assert r.status_code == 200
    assert_all_slots_free(render_slots)


def test_render_releases_slot_after_failure(render_slots, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("xelatex exploded")

    monkeypatch.setattr(render_module, "klartex_render", boom)

    r = client.post("/api/render", json=MINIMAL_BODY)

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
        results[index] = client.post("/api/render", json=MINIMAL_BODY).status_code

    threads = [
        threading.Thread(target=run, args=(i, ), daemon=True)
        for i in range(render_module.MAX_CONCURRENT_RENDERS)
    ]
    for t in threads:
        t.start()
    try:
        for _ in threads:
            assert in_render.acquire(timeout=10), "renders never started"

        r = client.post("/api/render", json=MINIMAL_BODY)
        assert r.status_code == 503
        assert r.json()["detail"]["type"] == "overloaded"
    finally:
        release.set()
        for t in threads:
            t.join(timeout=10)

    assert not any(t.is_alive() for t in threads)
    assert sorted(results.values()) == [200] * len(threads)
    assert_all_slots_free(render_slots)


def test_every_route_lives_under_api():
    """No route may escape the /api namespace — Caddy proxies only /api/*."""
    outside = sorted(
        route.path
        for route in app.routes
        if getattr(route, "path", "").startswith("/") and not route.path.startswith("/api")
    )
    assert outside == [], f"routes outside /api: {outside}"
