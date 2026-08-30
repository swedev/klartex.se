"""Render service — requires xelatex on PATH for the actual renders."""

import base64
import shutil
import threading

import pytest
from fastapi.testclient import TestClient

from klartex_render import __version__
from klartex_render import main as main_module
from klartex_render import render as render_module
from klartex_render.main import app

client = TestClient(app)

XELATEX = shutil.which("xelatex")
needs_xelatex = pytest.mark.skipif(XELATEX is None, reason="xelatex not on PATH")


def b64(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode()
    return base64.b64encode(data).decode()


def post_blocks(body_blocks, **extra):
    return client.post(
        "/render",
        json={"template": "_block", "data": {"body": body_blocks}, **extra},
    )


def post_block_error(body_blocks):
    """POST a block document expected to fail validation; return the detail."""
    r = post_blocks(body_blocks)
    assert r.status_code == 400, r.text
    return r.json()["detail"]


# --- Service surface --------------------------------------------------------


def test_health_reports_its_own_and_the_core_version():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["version"] == __version__
    # The backend compares this with its own after a deploy.
    assert body["klartex"]


def test_no_schema_is_published():
    """Internal service: nothing describes it to the outside."""
    assert client.get("/openapi.json").status_code == 404
    assert client.get("/docs").status_code == 404


# --- Rendering --------------------------------------------------------------


@needs_xelatex
def test_render_minimal_block_doc():
    r = client.post(
        "/render",
        json={
            "template": "_block",
            "data": {
                "lang": "sv",
                "body": [
                    {"type": "heading", "text": "Test"},
                    {"type": "text", "text": "Hello world."},
                ],
            },
        },
    )
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"


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

    r = client.post("/render", json={"template": "_block", "data": {}})
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["type"] == "validation_error"
    assert detail["path"] == []


def test_render_block_with_empty_type_carries_path():
    """An empty `type` satisfies the top-level schema but not the core.

    It reaches `_validate_blocks`, which reports it as
    `Block at body[i] is missing 'type'` — the third message form the
    path extraction has to recognise.
    """
    detail = post_block_error(
        [{"type": "heading", "text": "ok"}, {"type": "", "text": "x"}]
    )
    assert detail["type"] == "input_error"
    assert detail["path"] == ["body", 1]
    assert "body[1]" in detail["message"]


def test_block_error_path_returns_none_for_other_errors():
    assert render_module._block_error_path(ValueError("Unknown template")) is None


def test_render_unknown_template_returns_400():
    """An error with no block position carries no `path`."""
    r = client.post("/render", json={"template": "nope", "data": {}})
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["type"] == "input_error"
    assert "path" not in detail


def test_render_failure_is_a_500_render_error(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("xelatex exploded")

    monkeypatch.setattr(render_module, "klartex_render", boom)

    r = post_blocks([{"type": "heading", "text": "x"}])
    assert r.status_code == 500
    assert r.json()["detail"]["type"] == "render_error"


# --- Inline assets ----------------------------------------------------------
#
# The caller sends the bundle inline; the service writes it to a temporary
# directory for the duration of the call and hands that to xelatex.

# 1×1 transparent PNG — small enough to inline, real enough for graphicx.
PNG_1PX = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmM"
    "IQAAAABJRU5ErkJggg=="
)

LOGO_PAGE_TEMPLATE = (
    r"\fancyhead[R]{\includegraphics[height=1cm]{logo.png}}" "\n"
)

MINIMAL_BODY = [{"type": "heading", "text": "x"}]


@needs_xelatex
def test_render_with_inline_bundle_uses_the_asset():
    """A page template referencing an inline asset compiles against it."""
    r = post_blocks(
        MINIMAL_BODY,
        page_template_source=LOGO_PAGE_TEMPLATE,
        assets={"logo.png": PNG_1PX},
    )
    assert r.status_code == 200, r.text
    assert r.content[:4] == b"%PDF"


@needs_xelatex
def test_render_bundle_without_the_asset_fails():
    """The asset really comes from the request, not from the container."""
    r = post_blocks(MINIMAL_BODY, page_template_source=LOGO_PAGE_TEMPLATE)
    assert r.status_code == 500
    assert r.json()["detail"]["type"] == "render_error"


def test_assets_do_not_outlive_the_request(monkeypatch):
    """The temporary directory is gone once the response is written."""
    seen: list = []

    def capture(template, data, page_template_source=None, asset_dir=None):
        seen.append(asset_dir)
        assert (asset_dir / "logo.png").read_bytes()
        return b"%PDF-fake"

    monkeypatch.setattr(render_module, "klartex_render", capture)

    r = post_blocks(MINIMAL_BODY, assets={"logo.png": PNG_1PX})
    assert r.status_code == 200
    assert len(seen) == 1
    assert not seen[0].exists()


def test_render_without_a_bundle_passes_no_asset_dir(monkeypatch):
    """A plain render resolves its inputs exactly as the core does alone."""
    seen: list = []

    def capture(template, data, page_template_source=None, asset_dir=None):
        seen.append(asset_dir)
        return b"%PDF-fake"

    monkeypatch.setattr(render_module, "klartex_render", capture)

    assert post_blocks(MINIMAL_BODY).status_code == 200
    assert seen == [None]


@pytest.mark.parametrize(
    "filename",
    ["../escape.png", "sub/logo.png", ".hidden", "", "a" * 200],
    ids=["parent", "subdir", "dotfile", "empty", "too-long"],
)
def test_invalid_asset_filename_is_rejected(filename):
    """No caller can write outside the per-request temporary directory."""
    r = post_blocks(MINIMAL_BODY, assets={filename: PNG_1PX})
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["type"] == "input_error"
    assert "asset filename" in detail["message"]


def test_invalid_base64_asset_is_rejected():
    r = post_blocks(MINIMAL_BODY, assets={"logo.png": "not-base64!!!"})
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["type"] == "input_error"
    assert "base64" in detail["message"]


def test_oversized_asset_is_rejected():
    oversized = b64(b"x" * (render_module.MAX_ASSET_BYTES + 1))
    r = post_blocks(MINIMAL_BODY, assets={"logo.png": oversized})
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["type"] == "input_error"
    assert "exceeds limit" in detail["message"]


def test_too_many_assets_is_rejected():
    assets = {
        f"f{i}.png": PNG_1PX for i in range(render_module.MAX_ASSETS + 1)
    }
    r = post_blocks(MINIMAL_BODY, assets=assets)
    assert r.status_code == 400
    assert r.json()["detail"]["type"] == "input_error"


def test_oversized_page_template_source_is_rejected():
    source = "%" * (render_module.MAX_TEMPLATE_BYTES + 1)
    r = post_blocks(MINIMAL_BODY, page_template_source=source)
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["type"] == "input_error"
    assert "page_template_source" in detail["message"]


def test_oversized_request_is_rejected_before_the_body_is_read(monkeypatch):
    """The Content-Length header alone decides; the body is never parsed."""
    monkeypatch.setattr(main_module, "MAX_REQUEST_BYTES", 10)

    r = post_blocks(MINIMAL_BODY)

    assert r.status_code == 413
    assert r.json()["detail"]["type"] == "payload_too_large"


# --- Concurrency cap -------------------------------------------------------
#
# The tests below never invoke xelatex: klartex_render is replaced by a fake,
# so they exercise the semaphore alone and run anywhere.

MINIMAL_REQUEST = {"template": "_block", "data": {"body": MINIMAL_BODY}}


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

    r = client.post("/render", json=MINIMAL_REQUEST)

    assert r.status_code == 503
    assert r.headers["Retry-After"] == "5"
    assert r.json()["detail"]["type"] == "overloaded"


def test_render_releases_slot_after_success(render_slots, monkeypatch):
    monkeypatch.setattr(
        render_module, "klartex_render", lambda *a, **kw: b"%PDF-fake"
    )

    r = client.post("/render", json=MINIMAL_REQUEST)

    assert r.status_code == 200
    assert_all_slots_free(render_slots)


def test_render_releases_slot_after_failure(render_slots, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("xelatex exploded")

    monkeypatch.setattr(render_module, "klartex_render", boom)

    r = client.post("/render", json=MINIMAL_REQUEST)

    assert r.status_code == 500
    assert r.json()["detail"]["type"] == "render_error"
    assert_all_slots_free(render_slots)


def test_invalid_asset_does_not_take_a_slot(render_slots):
    """Input validation happens before the cap, so it cannot be starved."""
    for _ in range(render_module.MAX_CONCURRENT_RENDERS):
        assert render_slots.acquire(blocking=False)

    r = post_blocks(MINIMAL_BODY, assets={"../escape.png": PNG_1PX})

    assert r.status_code == 400


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
        results[index] = client.post("/render", json=MINIMAL_REQUEST).status_code

    threads = [
        threading.Thread(target=run, args=(i, ), daemon=True)
        for i in range(render_module.MAX_CONCURRENT_RENDERS)
    ]
    for t in threads:
        t.start()
    try:
        for _ in threads:
            assert in_render.acquire(timeout=10), "renders never started"

        r = client.post("/render", json=MINIMAL_REQUEST)
        assert r.status_code == 503
        assert r.json()["detail"]["type"] == "overloaded"
    finally:
        release.set()
        for t in threads:
            t.join(timeout=10)

    assert not any(t.is_alive() for t in threads)
    assert sorted(results.values()) == [200] * len(threads)
    assert_all_slots_free(render_slots)
