"""Discovery endpoints — pure passthrough, no xelatex needed."""

from fastapi.testclient import TestClient

from klartex_se.main import app

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_templates_lists_block_engine_and_recipes():
    r = client.get("/api/templates")
    assert r.status_code == 200
    names = {t["name"] for t in r.json()}
    # _block (block-engine) and at least one recipe always exist
    assert "_block" in names
    assert "protokoll" in names
    types = {t["name"]: t["type"] for t in r.json()}
    assert types["_block"] == "block-engine"
    assert types["protokoll"] == "recipe"


def test_template_schema_existing():
    r = client.get("/api/templates/_block/schema")
    assert r.status_code == 200
    schema = r.json()
    assert "$schema" in schema or "type" in schema


def test_template_schema_unknown():
    r = client.get("/api/templates/nonexistent/schema")
    assert r.status_code == 404


def test_blocks_includes_known_types():
    r = client.get("/api/blocks")
    assert r.status_code == 200
    names = {b["name"] for b in r.json()}
    # Sample of well-known block types
    assert {"heading", "text", "agenda", "signatures"} <= names


def test_block_schema_returns_the_schema():
    # Every block listed by /api/blocks must have a fetchable schema. Only the
    # 404 path was covered before, so this endpoint answered 500 in
    # production without any test noticing.
    for name in ("text", "heading", "agenda"):
        r = client.get(f"/api/blocks/{name}/schema")
        assert r.status_code == 200, f"{name}: {r.status_code} {r.text[:120]}"
        body = r.json()
        assert isinstance(body, dict) and body, f"{name}: empty schema"


def test_every_listed_block_has_a_schema():
    names = [b["name"] for b in client.get("/api/blocks").json()]
    broken = [n for n in names if client.get(f"/api/blocks/{n}/schema").status_code != 200]
    assert not broken, f"blocks listed but without a fetchable schema: {broken}"


def test_block_schema_unknown():
    r = client.get("/api/blocks/not-a-real-block/schema")
    assert r.status_code == 404
