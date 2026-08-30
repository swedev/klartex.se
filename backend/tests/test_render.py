"""Render endpoint — policy, bundle payloads and upstream passthrough.

The endpoint compiles nothing: it proxies to the render service. Every
test here replaces `render_pdf`, so what is exercised is the policy layer
— the tier gate, the page-template resolution, the in-flight cap and the
translation of the render service's answers. The compiler itself is
covered by render/tests/, and the two ends meet in test_contract.py.
"""

import base64
import threading

import pytest
from fastapi.testclient import TestClient

from klartex_se import page_templates as pt
from klartex_se import render as render_module
from klartex_se.auth import TOKEN_HOWTO
from klartex_se.main import app
from klartex_se.render_client import RenderUpstreamError

client = TestClient(app)

API_TOKEN = "test-token-do-not-use-in-prod"


@pytest.fixture(autouse=True)
def no_ambient_token(monkeypatch):
    """Anonymous is the default tier; tests that want a token opt in."""
    monkeypatch.delenv("API_TOKEN", raising=False)


@pytest.fixture
def api_token(monkeypatch):
    """Configure the instance token and hand back the matching header."""
    monkeypatch.setenv("API_TOKEN", API_TOKEN)
    return {"Authorization": f"Bearer {API_TOKEN}"}


@pytest.fixture
def fake_render(monkeypatch):
    """Replace the render call; the list collects the kwargs it was given."""
    calls: list[dict] = []

    def fake(template, data, page_template_source=None, assets=None):
        calls.append(
            {
                "template": template,
                "data": data,
                "page_template_source": page_template_source,
                "assets": assets,
            }
        )
        return b"%PDF-fake"

    monkeypatch.setattr(render_module, "render_pdf", fake)
    return calls


@pytest.fixture
def registry(tmp_path, monkeypatch):
    """An empty page-template registry for the duration of a test."""
    monkeypatch.setenv("PAGE_TEMPLATES_DIR", str(tmp_path))
    return tmp_path


LATEX_BLOCK = {"type": "latex", "body": "\\hrule"}

MINIMAL_BODY = {
    "template": "_block",
    "data": {"body": [{"type": "heading", "text": "x"}]},
}


def post_blocks(body_blocks, headers=None):
    return client.post(
        "/api/render",
        json={"template": "_block", "data": {"body": body_blocks}},
        headers=headers,
    )


def b64(s: str | bytes) -> str:
    if isinstance(s, str):
        s = s.encode()
    return base64.b64encode(s).decode()


# --- Page templates ---------------------------------------------------------


def test_render_unknown_page_template_returns_400(registry, fake_render):
    r = client.post(
        "/api/render",
        json={**MINIMAL_BODY, "page_template": "never-registered"},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["type"] == "unknown_page_template"
    assert fake_render == []


def test_builtin_page_template_is_merged_into_data(registry, fake_render):
    """Built-in names skip the bundle lookup and travel inside `data`."""
    r = client.post("/api/render", json={**MINIMAL_BODY, "page_template": "formal"})

    assert r.status_code == 200, r.text
    call = fake_render[0]
    assert call["data"]["page_template"] == "formal"
    assert call["page_template_source"] is None
    assert call["assets"] == {}


def test_bundle_travels_inline_with_the_render_call(registry, fake_render):
    """A registered bundle is read here and sent as source plus assets."""
    pt.save_bundle(
        "vkf",
        b64("\\fancyhead{VKF}\\includegraphics{logo.pdf}"),
        {"logo.pdf": b64(b"%PDF-logo"), "font.ttf": b64(b"ttf-bytes")},
    )

    r = client.post("/api/render", json={**MINIMAL_BODY, "page_template": "vkf"})

    assert r.status_code == 200, r.text
    call = fake_render[0]
    assert call["page_template_source"] == "\\fancyhead{VKF}\\includegraphics{logo.pdf}"
    assert call["assets"] == {
        "logo.pdf": b64(b"%PDF-logo"),
        "font.ttf": b64(b"ttf-bytes"),
    }
    # The name itself is not part of the render contract — the service has
    # no registry to look it up in.
    assert "page_template" not in call["data"]


def test_broken_bundle_returns_400(registry, fake_render):
    """A bundle whose asset is gone from disk is an input error, not a 500."""
    pt.save_bundle("vkf", b64("\\fancyhead{VKF}"), {"logo.pdf": b64(b"%PDF-logo")})
    (registry / "vkf" / "logo.pdf").unlink()

    r = client.post("/api/render", json={**MINIMAL_BODY, "page_template": "vkf"})

    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["type"] == "input_error"
    assert "logo.pdf" in detail["message"]
    assert fake_render == []


# --- Upstream passthrough ---------------------------------------------------


def upstream(status, detail, headers=None):
    """Make render_pdf answer as the render service did."""

    def raiser(*args, **kwargs):
        raise RenderUpstreamError(status, detail, headers)

    return raiser


def test_upstream_400_passes_through_unchanged(monkeypatch):
    detail = {
        "type": "input_error",
        "message": "Invalid 'text' block at body[1]: 'text' is a required property",
        "path": ["body", 1],
    }
    monkeypatch.setattr(render_module, "render_pdf", upstream(400, detail))

    r = client.post("/api/render", json=MINIMAL_BODY)

    assert r.status_code == 400
    # Not wrapped in another detail layer: the client sees what the render
    # service said, verbatim.
    assert r.json() == {"detail": detail}


def test_upstream_503_forwards_retry_after(monkeypatch):
    detail = {"type": "overloaded", "message": "Too many concurrent renders."}
    monkeypatch.setattr(
        render_module,
        "render_pdf",
        upstream(503, detail, {"Retry-After": "5"}),
    )

    r = client.post("/api/render", json=MINIMAL_BODY)

    assert r.status_code == 503
    assert r.headers["Retry-After"] == "5"
    assert r.json()["detail"]["type"] == "overloaded"


def test_unreachable_render_service_is_502(monkeypatch):
    detail = {
        "type": "render_unavailable",
        "message": "The render service did not answer. Retry in a few seconds.",
    }
    monkeypatch.setattr(render_module, "render_pdf", upstream(502, detail))

    r = client.post("/api/render", json=MINIMAL_BODY)

    assert r.status_code == 502
    assert r.json()["detail"]["type"] == "render_unavailable"
    # The internal address stays internal.
    assert "http://" not in r.json()["detail"]["message"]


def test_pdf_is_returned_as_an_attachment(fake_render):
    r = client.post("/api/render", json=MINIMAL_BODY)

    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"] == 'attachment; filename="document.pdf"'
    assert r.content == b"%PDF-fake"


# --- In-flight cap ----------------------------------------------------------


@pytest.fixture
def render_slots(monkeypatch):
    """Give each test its own semaphore, so a failure cannot leak slots."""
    slots = threading.BoundedSemaphore(render_module.MAX_INFLIGHT_RENDERS)
    monkeypatch.setattr(render_module, "_inflight_slots", slots)
    return slots


def assert_all_slots_free(slots):
    """Every slot is free — and no more than MAX_INFLIGHT_RENDERS exist."""
    acquired = [
        slots.acquire(blocking=False)
        for _ in range(render_module.MAX_INFLIGHT_RENDERS)
    ]
    extra = slots.acquire(blocking=False)
    for ok in acquired:
        if ok:
            slots.release()
    if extra:
        slots.release()
    assert all(acquired), "a render slot leaked"
    assert not extra, "more slots than MAX_INFLIGHT_RENDERS"


def test_render_returns_503_when_all_slots_taken(render_slots, fake_render):
    for _ in range(render_module.MAX_INFLIGHT_RENDERS):
        assert render_slots.acquire(blocking=False)

    r = client.post("/api/render", json=MINIMAL_BODY)

    assert r.status_code == 503
    assert r.headers["Retry-After"] == "5"
    assert r.json()["detail"]["type"] == "overloaded"
    assert fake_render == []


def test_render_releases_slot_after_success(render_slots, fake_render):
    r = client.post("/api/render", json=MINIMAL_BODY)

    assert r.status_code == 200
    assert_all_slots_free(render_slots)


def test_render_releases_slot_after_upstream_failure(render_slots, monkeypatch):
    monkeypatch.setattr(
        render_module,
        "render_pdf",
        upstream(500, {"type": "render_error", "message": "xelatex exploded"}),
    )

    r = client.post("/api/render", json=MINIMAL_BODY)

    assert r.status_code == 500
    assert r.json()["detail"]["type"] == "render_error"
    assert_all_slots_free(render_slots)


def test_render_releases_slot_after_a_broken_bundle(
    render_slots, registry, fake_render
):
    """The bundle is read inside the semaphore; failing there frees it."""
    pt.save_bundle("vkf", b64("\\fancyhead{VKF}"), {"logo.pdf": b64(b"%PDF-logo")})
    (registry / "vkf" / "logo.pdf").unlink()

    r = client.post("/api/render", json={**MINIMAL_BODY, "page_template": "vkf"})

    assert r.status_code == 400
    assert_all_slots_free(render_slots)


def test_render_third_concurrent_request_gets_503(render_slots, monkeypatch):
    """Two calls occupy both slots; a third is rejected immediately."""
    in_render = threading.Semaphore(0)
    release = threading.Event()

    def blocking_render(*args, **kwargs):
        in_render.release()
        assert release.wait(timeout=10), "render fake was never released"
        return b"%PDF-fake"

    monkeypatch.setattr(render_module, "render_pdf", blocking_render)

    results: dict[int, int] = {}

    def run(index):
        results[index] = client.post("/api/render", json=MINIMAL_BODY).status_code

    threads = [
        threading.Thread(target=run, args=(i, ), daemon=True)
        for i in range(render_module.MAX_INFLIGHT_RENDERS)
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


# --- Tiers: the `latex` block needs a token ---------------------------------


def test_anonymous_latex_block_returns_403():
    r = post_blocks([LATEX_BLOCK])
    assert r.status_code == 403
    detail = r.json()["detail"]
    assert detail["type"] == "token_required"
    assert detail["block_type"] == "latex"
    assert detail["path"] == ["body", 0]
    assert "latex" in detail["message"]
    assert TOKEN_HOWTO in detail["message"]
    # 403 is not an authentication challenge.
    assert "WWW-Authenticate" not in r.headers


@pytest.mark.parametrize(
    "blocks, expected_path",
    [
        (
            [{"type": "columns", "items": [[{"type": "text", "text": "a"}],
                                           [LATEX_BLOCK]]}],
            ["body", 0, "items", 1, 0],
        ),
        (
            [{"type": "list", "items": [{"content": [LATEX_BLOCK]}]}],
            ["body", 0, "items", 0, "content", 0],
        ),
        (
            [{"type": "clause", "content": [LATEX_BLOCK]}],
            ["body", 0, "content", 0],
        ),
    ],
    ids=["columns", "list", "clause"],
)
def test_anonymous_nested_latex_block_returns_403(blocks, expected_path):
    r = post_blocks(blocks)
    assert r.status_code == 403
    detail = r.json()["detail"]
    assert detail["type"] == "token_required"
    assert detail["path"] == expected_path


def test_latex_gate_precedes_the_semaphore(render_slots, fake_render):
    """The 403 does not depend on a free slot, and renders nothing."""
    for _ in range(render_module.MAX_INFLIGHT_RENDERS):
        assert render_slots.acquire(blocking=False)

    r = post_blocks([LATEX_BLOCK])

    assert r.status_code == 403
    assert r.json()["detail"]["type"] == "token_required"
    assert fake_render == []


def test_token_unlocks_the_latex_block(api_token, fake_render):
    r = post_blocks([LATEX_BLOCK], headers=api_token)
    assert r.status_code == 200, r.text
    assert len(fake_render) == 1


def test_wrong_token_is_401_not_anonymous(api_token, fake_render):
    """A presented but wrong token fails loudly rather than degrading."""
    wrong = {"Authorization": "Bearer nope"}

    r = post_blocks([{"type": "heading", "text": "x"}], headers=wrong)
    assert r.status_code == 401
    assert r.json()["detail"]["type"] == "invalid_token"
    assert r.headers["WWW-Authenticate"] == "Bearer"
    assert fake_render == []


def test_wrong_token_with_latex_is_401_not_403(api_token):
    """Verification runs before the block policy."""
    r = post_blocks([LATEX_BLOCK], headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401
    assert r.json()["detail"]["type"] == "invalid_token"


def test_token_without_bearer_prefix_is_401(api_token):
    r = post_blocks([LATEX_BLOCK], headers={"Authorization": API_TOKEN})
    assert r.status_code == 401
    assert r.json()["detail"]["type"] == "token_required"


def test_non_ascii_token_is_401_not_500(api_token):
    """Header bytes outside ASCII must not blow up the comparison."""
    r = post_blocks(
        [{"type": "heading", "text": "x"}],
        # Latin-1 on the wire, which is how Starlette decodes header bytes.
        headers={"Authorization": b"Bearer nyckel-med-\xe5\xe4\xf6"},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["type"] == "invalid_token"


def test_presented_token_without_configured_token_is_503(fake_render):
    r = post_blocks(
        [{"type": "heading", "text": "x"}],
        headers={"Authorization": f"Bearer {API_TOKEN}"},
    )
    assert r.status_code == 503
    assert r.json()["detail"]["type"] == "token_not_configured"
    assert fake_render == []


def test_anonymous_render_works_without_a_configured_token(fake_render):
    """The release smoke test renders anonymously with no token in env."""
    r = post_blocks([{"type": "heading", "text": "x"}])
    assert r.status_code == 200, r.text
    assert len(fake_render) == 1


def test_recipe_template_is_not_scanned_for_latex(fake_render):
    """The policy covers `_block` only; a recipe never interprets blocks."""
    r = client.post(
        "/api/render",
        json={
            "template": "faktura",
            "data": {"body": [LATEX_BLOCK], "rader": [{"type": "latex"}]},
        },
    )
    assert r.status_code != 403


def test_openapi_documents_render_responses():
    responses = client.get("/api/openapi.json").json()["paths"]["/api/render"]["post"][
        "responses"
    ]
    assert {"401", "403", "502"} <= set(responses)
    assert "render_unavailable" in responses["502"]["description"]
    description = responses["503"]["description"]
    assert "overloaded" in description
    assert "token_not_configured" in description


# --- find_latex_block ------------------------------------------------------


@pytest.mark.parametrize("body", [None, [], {}, "text", 5])
def test_find_latex_block_returns_none_without_a_latex_block(body):
    assert render_module.find_latex_block(body) is None


def test_find_latex_block_skips_non_container_entries():
    body = ["a", 1, None, {"type": "text", "text": "x"}]
    assert render_module.find_latex_block(body) is None


def test_find_latex_block_returns_first_in_document_order():
    body = [
        {"type": "columns", "items": [[LATEX_BLOCK], [LATEX_BLOCK]]},
        LATEX_BLOCK,
    ]
    assert render_module.find_latex_block(body) == ["body", 0, "items", 0, 0]


@pytest.mark.parametrize(
    "block",
    [
        {
            "type": "parties",
            "party1": {"name": "Alfa AB", "type": "latex"},
            "party2": {"name": "Beta AB"},
        },
        {"type": "signatures", "parties": [{"name": "Alfa AB", "type": "latex"}]},
    ],
    ids=["parties", "signatures"],
)
def test_find_latex_block_ignores_ordinary_data(block):
    """Only block positions count — a data field is not a block.

    `parties.party1` and `signatures.parties[i]` permit extra properties,
    so a party may legitimately carry `type`. The core never reads those
    as blocks and renders the document, so neither may the gate reject it.
    """
    assert render_module.find_latex_block([block]) is None


def test_anonymous_party_carrying_a_type_field_still_renders(fake_render):
    """The false positive above, end to end."""
    r = post_blocks(
        [
            {
                "type": "parties",
                "party1": {"name": "Alfa AB", "type": "latex"},
                "party2": {"name": "Beta AB"},
            }
        ]
    )
    assert r.status_code == 200, r.text
    assert len(fake_render) == 1


def test_find_latex_block_ignores_non_carrier_properties():
    """An unknown block's own properties are data, not a block list."""
    body = [{"type": "future", "panes": {"left": {"stack": [LATEX_BLOCK]}}}]
    assert render_module.find_latex_block(body) is None


def test_carrier_map_matches_the_core():
    """Pin the local carrier map against klartex's own.

    `render._child_block_lists` mirrors `klartex.renderer._child_block_lists`
    so production code does not depend on a private core name. If the core
    starts nesting blocks in a type this map does not know, an anonymous
    caller could hide a `latex` block there — so that must fail here rather
    than pass silently.
    """
    from klartex.block_engine import KNOWN_BLOCK_TYPES
    from klartex.renderer import _child_block_lists as core_carriers

    for block_type in sorted(KNOWN_BLOCK_TYPES):
        probe = {
            "type": block_type,
            "items": [{"content": [LATEX_BLOCK]}, [LATEX_BLOCK]],
            "content": [LATEX_BLOCK],
        }
        ours = [blocks for blocks, _ in render_module._child_block_lists(probe, [])]
        theirs = [blocks for _, blocks in core_carriers(probe)]
        assert ours == theirs, f"carrier mismatch for block type {block_type!r}"


def test_find_latex_block_survives_deep_nesting():
    """Deeply nested carriers must not raise RecursionError."""
    body: object = [LATEX_BLOCK]
    for _ in range(5_000):
        body = [{"type": "clause", "content": body}]
    assert render_module.find_latex_block(body) is not None


def test_every_route_lives_under_api():
    """No route may escape the /api namespace — Caddy proxies only /api/*."""
    outside = sorted(
        route.path
        for route in app.routes
        if getattr(route, "path", "").startswith("/") and not route.path.startswith("/api")
    )
    assert outside == [], f"routes outside /api: {outside}"
