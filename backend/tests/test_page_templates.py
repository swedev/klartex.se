"""Page-template registry — storage layer + HTTP routes.

Storage tests don't need xelatex. Render-via-name tests live in test_render.py.
"""

import base64
import os

import pytest
from fastapi.testclient import TestClient

from klartex_se.main import app
from klartex_se import page_templates as pt

API_TOKEN = "test-token-do-not-use-in-prod"
AUTH = {"Authorization": f"Bearer {API_TOKEN}"}


@pytest.fixture(autouse=True)
def isolated_registry(tmp_path, monkeypatch):
    """Each test gets a fresh registry dir + api token."""
    monkeypatch.setenv("PAGE_TEMPLATES_DIR", str(tmp_path))
    monkeypatch.setenv("API_TOKEN", API_TOKEN)
    yield


@pytest.fixture
def client():
    return TestClient(app)


def b64(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode()
    return base64.b64encode(data).decode()


# --- Storage layer ----------------------------------------------------------

def test_save_and_list():
    pt.save_bundle("vkf", b64("\\fancyhead{VKF}"), {"logo.pdf": b64(b"%PDF-fake")})
    bundles = pt.list_bundles()
    assert len(bundles) == 1
    assert bundles[0]["name"] == "vkf"
    assert bundles[0]["asset_names"] == ["logo.pdf"]


def test_get_returns_metadata_not_content():
    pt.save_bundle(
        "x",
        b64("template"),
        {"a.pdf": b64(b"x")},
        description="hello",
    )
    meta = pt.get_bundle("x")
    assert meta["name"] == "x"
    assert meta["description"] == "hello"
    # No template/asset bytes in metadata.
    assert "template" not in meta
    assert "assets" not in meta


def test_overwrite_required_for_replace():
    pt.save_bundle("a", b64("v1"), {})
    with pytest.raises(pt.PageTemplateExists):
        pt.save_bundle("a", b64("v2"), {})
    pt.save_bundle("a", b64("v2"), {}, overwrite=True)
    # Bundle now has v2 content.
    path = pt.get_bundle_path("a")
    assert (path / pt.TEMPLATE_FILENAME).read_text() == "v2"


def test_overwrite_preserves_created_at():
    pt.save_bundle("a", b64("v1"), {})
    before = pt.get_bundle("a")["created_at"]
    pt.save_bundle("a", b64("v2"), {}, overwrite=True)
    after = pt.get_bundle("a")
    assert after["created_at"] == before
    assert "updated_at" in after


def test_invalid_name_rejected():
    with pytest.raises(pt.PageTemplateError):
        pt.save_bundle("HasCaps", b64("x"), {})
    with pytest.raises(pt.PageTemplateError):
        pt.save_bundle("../escape", b64("x"), {})
    with pytest.raises(pt.PageTemplateError):
        pt.save_bundle("", b64("x"), {})


def test_invalid_asset_name_rejected():
    with pytest.raises(pt.PageTemplateError):
        pt.save_bundle("ok", b64("x"), {"../escape.pdf": b64(b"x")})


def test_template_size_limit():
    too_big = b"x" * (pt.MAX_TEMPLATE_BYTES + 1)
    with pytest.raises(pt.PageTemplateError):
        pt.save_bundle("big", b64(too_big), {})


def test_asset_count_limit():
    assets = {f"f{i}.pdf": b64(b"x") for i in range(pt.MAX_ASSETS + 1)}
    with pytest.raises(pt.PageTemplateError):
        pt.save_bundle("many", b64("x"), assets)


def test_delete():
    pt.save_bundle("doomed", b64("x"), {})
    pt.delete_bundle("doomed")
    with pytest.raises(pt.PageTemplateNotFound):
        pt.get_bundle("doomed")


# --- HTTP routes ------------------------------------------------------------

def test_list_empty(client):
    r = client.get("/page-templates")
    assert r.status_code == 200
    assert r.json() == []


def test_create_requires_admin(client):
    body = {"name": "vkf", "template": b64("x"), "assets": {}}
    # No auth header.
    r = client.post("/page-templates", json=body)
    assert r.status_code == 401
    # With auth.
    r = client.post("/page-templates", json=body, headers=AUTH)
    assert r.status_code == 201
    assert r.json()["name"] == "vkf"


def test_create_then_get_then_delete(client):
    body = {
        "name": "demo",
        "template": b64("\\fancyhead{Demo}"),
        "assets": {"logo.pdf": b64(b"%PDF-")},
        "description": "demo bundle",
    }
    r = client.post("/page-templates", json=body, headers=AUTH)
    assert r.status_code == 201

    r = client.get("/page-templates/demo")
    assert r.status_code == 200
    assert r.json()["description"] == "demo bundle"

    r = client.get("/page-templates")
    assert {b["name"] for b in r.json()} == {"demo"}

    r = client.delete("/page-templates/demo", headers=AUTH)
    assert r.status_code == 204
    r = client.get("/page-templates/demo")
    assert r.status_code == 404


def test_create_conflict_then_overwrite(client):
    body = {"name": "x", "template": b64("v1"), "assets": {}}
    r = client.post("/page-templates", json=body, headers=AUTH)
    assert r.status_code == 201
    r = client.post("/page-templates", json=body, headers=AUTH)
    assert r.status_code == 409
    body["overwrite"] = True
    body["template"] = b64("v2")
    r = client.post("/page-templates", json=body, headers=AUTH)
    assert r.status_code == 201


def test_unconfigured_token_returns_503(client, monkeypatch):
    monkeypatch.delenv("API_TOKEN", raising=False)
    r = client.post(
        "/page-templates",
        json={"name": "x", "template": b64("y"), "assets": {}},
        headers=AUTH,
    )
    assert r.status_code == 503


def test_invalid_base64_returns_400(client):
    r = client.post(
        "/page-templates",
        json={"name": "x", "template": "not-base64!!!", "assets": {}},
        headers=AUTH,
    )
    assert r.status_code == 400
