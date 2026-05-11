"""Discovery endpoints — pure passthrough, no xelatex needed."""

from fastapi.testclient import TestClient

from klartex_se.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_templates_lists_block_engine_and_recipes():
    r = client.get("/templates")
    assert r.status_code == 200
    names = {t["name"] for t in r.json()}
    # _block (block-engine) and at least one recipe always exist
    assert "_block" in names
    assert "protokoll" in names
    types = {t["name"]: t["type"] for t in r.json()}
    assert types["_block"] == "block-engine"
    assert types["protokoll"] == "recipe"


def test_template_schema_existing():
    r = client.get("/templates/_block/schema")
    assert r.status_code == 200
    schema = r.json()
    assert "$schema" in schema or "type" in schema


def test_template_schema_unknown():
    r = client.get("/templates/nonexistent/schema")
    assert r.status_code == 404


def test_blocks_includes_known_types():
    r = client.get("/blocks")
    assert r.status_code == 200
    names = {b["name"] for b in r.json()}
    # Sample of well-known block types
    assert {"heading", "text", "agenda", "signatures"} <= names


def test_block_schema_unknown():
    r = client.get("/blocks/not-a-real-block/schema")
    assert r.status_code == 404
