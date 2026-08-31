"""Render endpoint — requires xelatex to be on PATH for actual renders."""

import base64
import shutil
import threading

import pytest
from fastapi.testclient import TestClient

from klartex_se import page_templates as pt
from klartex_se import render as render_module
from klartex_se.auth import TOKEN_HOWTO
from klartex_se.main import app

client = TestClient(app)

XELATEX = shutil.which("xelatex")
needs_xelatex = pytest.mark.skipif(XELATEX is None, reason="xelatex not on PATH")

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
    """Replace the compiler, so tier tests never invoke xelatex."""
    calls: list[tuple] = []

    def fake(*args, **kwargs):
        calls.append((args, kwargs))
        return b"%PDF-fake"

    monkeypatch.setattr(render_module, "klartex_render", fake)
    return calls


LATEX_BLOCK = {"type": "latex", "body": "\\hrule"}


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


SLOT_FORM = {
    "header": {
        "variant": "letterhead",
        "fields": {"org_name": "Föreningen Klartex"},
    },
    "footer": "pagenumber",
}


def test_render_page_template_object_reaches_the_core_unchanged(fake_render):
    """An object is klartex's slot form; the endpoint moves it, nothing else."""
    r = client.post(
        "/api/render",
        json={
            "template": "_block",
            "data": {"body": [{"type": "heading", "text": "x"}]},
            "page_template": SLOT_FORM,
        },
    )
    assert r.status_code == 200, r.text
    (_, data), kwargs = fake_render[0]
    assert data["page_template"] == SLOT_FORM
    assert kwargs["header_source"] is None
    assert kwargs["asset_dir"] is None


def test_render_page_template_object_is_validated_by_the_core():
    """The slot form is the core's contract, so the core rejects a bad one."""
    r = client.post(
        "/api/render",
        json={
            "template": "_block",
            "data": {"body": [{"type": "heading", "text": "x"}]},
            "page_template": {"header": {"variant": "no-such-variant"}},
        },
    )
    assert r.status_code == 400, r.text
    assert r.json()["detail"]["type"] == "validation_error"


@needs_xelatex
def test_render_page_template_object_renders():
    r = client.post(
        "/api/render",
        json={
            "template": "_block",
            "data": {"body": [{"type": "heading", "text": "x"}]},
            "page_template": SLOT_FORM,
        },
    )
    assert r.status_code == 200, r.text
    assert r.content[:4] == b"%PDF"


# --- Registered bundles: one source owning the header slot ------------------


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    """Register a one-source bundle and hand back (name, source, dir)."""
    monkeypatch.setenv("PAGE_TEMPLATES_DIR", str(tmp_path))
    source = "\\fancyhead[L]{VKF}"
    pt.save_bundle("vkf", b64(source), {"logo.pdf": b64(b"%PDF-fake")})
    return "vkf", source, tmp_path / "vkf"


def test_bundle_is_sent_as_the_header_source(bundle, fake_render):
    name, source, bundle_dir = bundle
    r = client.post(
        "/api/render",
        json={
            "template": "_block",
            "data": {"body": [{"type": "heading", "text": "x"}]},
            "page_template": name,
        },
    )
    assert r.status_code == 200, r.text
    (_, data), kwargs = fake_render[0]
    assert kwargs["header_source"] == source
    assert kwargs["asset_dir"] == bundle_dir
    assert data["page_template"] == {"footer": None}


def test_bundle_empties_the_footer_and_keeps_the_other_settings(
    bundle, fake_render
):
    """The bundle owns the whole page, so a caller's footer loses to it."""
    name, _, _ = bundle
    r = client.post(
        "/api/render",
        json={
            "template": "_block",
            "data": {
                "body": [{"type": "heading", "text": "x"}],
                "page_template": {"footer": {"variant": "columns"}, "font": "Futura"},
            },
            "page_template": name,
        },
    )
    assert r.status_code == 200, r.text
    (_, data), _kwargs = fake_render[0]
    assert data["page_template"] == {"footer": None, "font": "Futura"}


@needs_xelatex
def test_bundle_renders(bundle):
    """The whole-page source compiles as the header slot, end to end."""
    name, _, _ = bundle
    r = client.post(
        "/api/render",
        json={
            "template": "_block",
            "data": {"body": [{"type": "heading", "text": "x"}]},
            "page_template": name,
        },
    )
    assert r.status_code == 200, r.text
    assert r.content[:4] == b"%PDF"


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
    """The 403 does not depend on a free render slot, and renders nothing."""
    for _ in range(render_module.MAX_CONCURRENT_RENDERS):
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


def test_openapi_documents_render_auth_responses():
    responses = client.get("/api/openapi.json").json()["paths"]["/api/render"]["post"][
        "responses"
    ]
    assert {"401", "403"} <= set(responses)
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
