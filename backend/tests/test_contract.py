"""The backend → render contract, exercised end to end in one process.

Both halves of the split are Python, so the whole chain can run without
Docker: the backend's HTTP client is pointed at a Starlette TestClient
driving the render app, which is a synchronous httpx.Client subclass with
its own transport and accepts absolute URLs whatever the hostname says.

What that buys over mocking either side is the part no unit test can see:
that the payload the backend builds really parses as the render service's
request model, and that the error bodies the render service produces
really survive the backend's validation and reach the client unchanged.
Without xelatex the validation and input paths still run; the two tests
that need a real PDF skip themselves, as they do in CI.
"""

import base64
import shutil

import pytest
from fastapi.testclient import TestClient

from klartex_render.main import app as render_app
from klartex_se import page_templates as pt
from klartex_se import render_client
from klartex_se.main import app as backend_app
from klartex_se.render_client import RenderUpstreamError, render_pdf

client = TestClient(backend_app)

XELATEX = shutil.which("xelatex")
needs_xelatex = pytest.mark.skipif(XELATEX is None, reason="xelatex not on PATH")


@pytest.fixture(autouse=True)
def wired_to_render(monkeypatch):
    """Send the backend's render calls to the render app in-process."""
    monkeypatch.delenv("API_TOKEN", raising=False)
    render_client_stub = TestClient(render_app)
    monkeypatch.setattr(render_client, "_client", lambda: render_client_stub)


@pytest.fixture
def registry(tmp_path, monkeypatch):
    monkeypatch.setenv("PAGE_TEMPLATES_DIR", str(tmp_path))
    return tmp_path


def b64(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode()
    return base64.b64encode(data).decode()


def post_blocks(body_blocks, **extra):
    return client.post(
        "/api/render",
        json={"template": "_block", "data": {"body": body_blocks}, **extra},
    )


# 1x1 transparent PNG — small enough to inline, real enough for graphicx.
PNG_1PX = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmM"
    "IQAAAABJRU5ErkJggg=="
)

# A page template that actually uses its asset, so a successful render
# proves the bundle reached xelatex rather than merely travelled.
LOGO_TEMPLATE = r"\fancyhead[R]{\includegraphics[height=1cm]{logo.png}}" "\n"


def test_validation_error_reaches_the_client_with_its_path(registry):
    """A schema violation keeps its type and its path across the hop."""
    r = client.post("/api/render", json={"template": "_block", "data": {}})

    assert r.status_code == 400, r.text
    detail = r.json()["detail"]
    assert detail["type"] == "validation_error"
    assert detail["path"] == []


def test_block_error_path_reaches_the_client(registry):
    r = post_blocks([{"type": "heading", "text": "ok"}, {"type": "text"}])

    assert r.status_code == 400, r.text
    detail = r.json()["detail"]
    assert detail["type"] == "input_error"
    assert detail["path"] == ["body", 1]
    assert "body[1]" in detail["message"]


def test_nested_block_error_path_reaches_the_client(registry):
    columns = [[{"type": "text", "text": "a"}], [{"type": "text", "text": 123}]]
    r = post_blocks([{"type": "columns", "items": columns}])

    assert r.status_code == 400, r.text
    assert r.json()["detail"]["path"] == ["body", 0, "items", 1, 0, "text"]


def test_unknown_template_reaches_the_client(registry):
    r = client.post("/api/render", json={"template": "nope", "data": {}})

    assert r.status_code == 400, r.text
    detail = r.json()["detail"]
    assert detail["type"] == "input_error"
    assert "path" not in detail


def test_the_render_service_never_answers_422(registry):
    """A payload the render model rejects would surface as 502, not 400.

    This is the test that fails if the two request shapes drift apart.
    """
    for body in ([], [{"type": "heading", "text": "x"}]):
        r = post_blocks(body)
        assert r.status_code != 502, r.text


def test_asset_names_are_validated_by_the_render_service():
    """The renderer re-checks what the registry checked. Pinned from here.

    The registry cannot store such a name, so only a faulty backend could
    send one — and the answer must still be a 400 rather than a file
    written outside the per-request directory.
    """
    with pytest.raises(RenderUpstreamError) as excinfo:
        render_pdf(
            "_block",
            {"body": [{"type": "heading", "text": "x"}]},
            page_template_source="",
            assets={"../escape.png": PNG_1PX},
        )

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail["type"] == "input_error"
    assert "escape.png" in excinfo.value.detail["message"]


def test_invalid_base64_is_an_input_error():
    with pytest.raises(RenderUpstreamError) as excinfo:
        render_pdf(
            "_block",
            {"body": [{"type": "heading", "text": "x"}]},
            assets={"logo.png": "not base64!!"},
        )

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail["type"] == "input_error"


@needs_xelatex
def test_minimal_document_renders_end_to_end(registry):
    r = client.post(
        "/api/render",
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


@needs_xelatex
def test_registered_bundle_renders_end_to_end(registry):
    """A bundle stored here is read, inlined, and used by xelatex there."""
    pt.save_bundle("vkf", b64(LOGO_TEMPLATE), {"logo.png": PNG_1PX})

    r = post_blocks(
        [{"type": "heading", "text": "Med logotyp"}], page_template="vkf"
    )

    assert r.status_code == 200, r.text
    assert r.content[:4] == b"%PDF"
