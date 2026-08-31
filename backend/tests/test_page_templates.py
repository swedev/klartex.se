"""Page-template registry — storage layer + HTTP routes.

Storage tests don't need xelatex. Render-via-name tests live in test_render.py.
"""

import base64

import pytest
from fastapi.testclient import TestClient

from klartex_se.auth import TOKEN_HOWTO
from klartex_se.main import app
from klartex_se import page_templates as pt

API_TOKEN = "test-token-do-not-use-in-prod"
AUTH = {"Authorization": f"Bearer {API_TOKEN}"}
WRONG_AUTH = {"Authorization": "Bearer nope"}


@pytest.fixture(autouse=True)
def isolated_registry(tmp_path, monkeypatch):
    """Each test gets a fresh registry dir + API token."""
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


# --- Bundle payloads --------------------------------------------------------
#
# The render service has no volume and no registry, so a bundle travels
# inline with the render call. load_bundle_payload is what turns stored
# files into that payload.

def test_load_bundle_payload_returns_source_and_assets():
    pt.save_bundle(
        "vkf",
        b64("\\fancyhead{VKF}"),
        {"logo.pdf": b64(b"%PDF-logo"), "font.ttf": b64(b"ttf")},
    )

    source, assets = pt.load_bundle_payload("vkf")

    assert source == "\\fancyhead{VKF}"
    assert assets == {"logo.pdf": b64(b"%PDF-logo"), "font.ttf": b64(b"ttf")}


def test_load_bundle_payload_without_assets():
    pt.save_bundle("plain", b64("\\fancyhead{P}"), {})

    source, assets = pt.load_bundle_payload("plain")

    assert source == "\\fancyhead{P}"
    assert assets == {}


def test_load_bundle_payload_keeps_non_ascii_source():
    pt.save_bundle("sv", b64("\\fancyhead{Årsmöte}"), {})

    source, _ = pt.load_bundle_payload("sv")

    assert source == "\\fancyhead{Årsmöte}"


def test_load_bundle_payload_missing_asset_is_a_broken_bundle(tmp_path):
    pt.save_bundle("vkf", b64("x"), {"logo.pdf": b64(b"%PDF-logo")})
    (tmp_path / "vkf" / "logo.pdf").unlink()

    with pytest.raises(pt.PageTemplateError, match="logo.pdf"):
        pt.load_bundle_payload("vkf")


def test_load_bundle_payload_rejects_a_source_that_is_not_utf8(tmp_path):
    pt.save_bundle("latin", b64("x"), {})
    (tmp_path / "latin" / pt.TEMPLATE_FILENAME).write_bytes(b"\\head{\xe5\xe4\xf6}")

    with pytest.raises(pt.PageTemplateError, match="UTF-8"):
        pt.load_bundle_payload("latin")


def test_load_bundle_payload_rejects_an_asset_name_from_outside(tmp_path):
    """Metadata edited on disk cannot make the reader leave the bundle."""
    pt.save_bundle("vkf", b64("x"), {})
    meta = tmp_path / "vkf" / pt.METADATA_FILENAME
    meta.write_text(meta.read_text().replace('"asset_names": []',
                                             '"asset_names": ["../secret.pdf"]'))

    with pytest.raises(pt.PageTemplateError, match="secret.pdf"):
        pt.load_bundle_payload("vkf")


def test_load_bundle_payload_reports_a_deleted_bundle_as_not_found():
    with pytest.raises(pt.PageTemplateNotFound):
        pt.load_bundle_payload("never-registered")


def test_load_bundle_payload_rejects_unreadable_metadata(tmp_path):
    """Metadata edited into invalid JSON is a broken bundle, not a 500.

    get_bundle_path only proves the file exists, so this is the first read
    that parses it.
    """
    pt.save_bundle("vkf", b64("x"), {})
    (tmp_path / "vkf" / pt.METADATA_FILENAME).write_text("{not json")

    with pytest.raises(pt.PageTemplateError, match=pt.METADATA_FILENAME):
        pt.load_bundle_payload("vkf")


def test_load_bundle_payload_reports_metadata_vanishing_as_not_found(monkeypatch):
    """Deleted between the existence check and the metadata read."""
    pt.save_bundle("vkf", b64("x"), {})

    def vanished(bundle_dir):
        raise FileNotFoundError(bundle_dir / pt.METADATA_FILENAME)

    monkeypatch.setattr(pt, "_load_metadata", vanished)

    with pytest.raises(pt.PageTemplateNotFound):
        pt.load_bundle_payload("vkf")


# --- HTTP routes ------------------------------------------------------------

def test_list_empty(client):
    r = client.get("/api/page-templates")
    assert r.status_code == 200
    assert r.json() == []


def test_create_requires_api_token(client):
    body = {"name": "vkf", "template": b64("x"), "assets": {}}
    # No auth header.
    r = client.post("/api/page-templates", json=body)
    assert r.status_code == 401
    detail = r.json()["detail"]
    assert detail["type"] == "token_required"
    assert TOKEN_HOWTO in detail["message"]
    assert r.headers["WWW-Authenticate"] == "Bearer"
    # With auth.
    r = client.post("/api/page-templates", json=body, headers=AUTH)
    assert r.status_code == 201
    assert r.json()["name"] == "vkf"


def test_create_with_wrong_token_returns_401(client):
    r = client.post(
        "/api/page-templates",
        json={"name": "vkf", "template": b64("x"), "assets": {}},
        headers=WRONG_AUTH,
    )
    assert r.status_code == 401
    detail = r.json()["detail"]
    assert detail["type"] == "invalid_token"
    assert TOKEN_HOWTO in detail["message"]
    assert r.headers["WWW-Authenticate"] == "Bearer"


def test_delete_requires_api_token(client):
    r = client.post(
        "/api/page-templates",
        json={"name": "doomed", "template": b64("x"), "assets": {}},
        headers=AUTH,
    )
    assert r.status_code == 201

    r = client.delete("/api/page-templates/doomed")
    assert r.status_code == 401
    assert r.json()["detail"]["type"] == "token_required"

    r = client.delete("/api/page-templates/doomed", headers=WRONG_AUTH)
    assert r.status_code == 401
    assert r.json()["detail"]["type"] == "invalid_token"

    r = client.delete("/api/page-templates/doomed", headers=AUTH)
    assert r.status_code == 204


def test_create_then_get_then_delete(client):
    body = {
        "name": "demo",
        "template": b64("\\fancyhead{Demo}"),
        "assets": {"logo.pdf": b64(b"%PDF-")},
        "description": "demo bundle",
    }
    r = client.post("/api/page-templates", json=body, headers=AUTH)
    assert r.status_code == 201

    r = client.get("/api/page-templates/demo")
    assert r.status_code == 200
    assert r.json()["description"] == "demo bundle"

    r = client.get("/api/page-templates")
    assert {b["name"] for b in r.json()} == {"demo"}

    r = client.delete("/api/page-templates/demo", headers=AUTH)
    assert r.status_code == 204
    r = client.get("/api/page-templates/demo")
    assert r.status_code == 404


def test_create_conflict_then_overwrite(client):
    body = {"name": "x", "template": b64("v1"), "assets": {}}
    r = client.post("/api/page-templates", json=body, headers=AUTH)
    assert r.status_code == 201
    r = client.post("/api/page-templates", json=body, headers=AUTH)
    assert r.status_code == 409
    body["overwrite"] = True
    body["template"] = b64("v2")
    r = client.post("/api/page-templates", json=body, headers=AUTH)
    assert r.status_code == 201


@pytest.mark.parametrize("unset", [True, False])
def test_unconfigured_token_returns_503(client, monkeypatch, unset):
    """A missing and an empty API_TOKEN both mean "not configured"."""
    if unset:
        monkeypatch.delenv("API_TOKEN", raising=False)
    else:
        monkeypatch.setenv("API_TOKEN", "")

    r = client.post(
        "/api/page-templates",
        json={"name": "x", "template": b64("y"), "assets": {}},
        headers=AUTH,
    )
    assert r.status_code == 503
    assert r.json()["detail"]["type"] == "token_not_configured"

    # Reads stay open on an instance without a token.
    assert client.get("/api/page-templates").status_code == 200
    assert client.get("/api/templates").status_code == 200


def test_openapi_documents_write_auth_responses(client):
    paths = client.get("/api/openapi.json").json()["paths"]
    assert {"401", "503"} <= set(paths["/api/page-templates"]["post"]["responses"])
    assert {"401", "503"} <= set(
        paths["/api/page-templates/{name}"]["delete"]["responses"]
    )


def test_invalid_base64_returns_400(client):
    r = client.post(
        "/api/page-templates",
        json={"name": "x", "template": "not-base64!!!", "assets": {}},
        headers=AUTH,
    )
    assert r.status_code == 400
