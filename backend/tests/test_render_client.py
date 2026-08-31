"""The HTTP client for the render service, against a mocked transport.

What is pinned here is the passthrough rule: which upstream answers the
client is allowed to hand on unchanged, and that everything else becomes
one `502 render_unavailable` that says nothing about the internals.
"""

import json

import httpx
import pytest

from klartex_se import render_client
from klartex_se.render_client import (
    RENDER_URL,
    RenderUpstreamError,
    render_pdf,
)


@pytest.fixture
def upstream(monkeypatch):
    """Answer render calls with whatever the handler returns."""

    def install(handler):
        calls: list[httpx.Request] = []

        def record(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return handler(request)

        client = httpx.Client(transport=httpx.MockTransport(record))
        monkeypatch.setattr(render_client, "_client", lambda: client)
        return calls

    return install


def answering(status, **kwargs):
    return lambda handler_request: httpx.Response(status, **kwargs)


def test_200_returns_the_pdf_bytes(upstream):
    calls = upstream(answering(200, content=b"%PDF-1.7 ..."))

    assert render_pdf("_block", {"body": []}) == b"%PDF-1.7 ..."
    assert str(calls[0].url) == f"{RENDER_URL}/render"


def test_the_request_carries_the_full_contract(upstream):
    calls = upstream(answering(200, content=b"%PDF"))

    render_pdf(
        "_block",
        {"body": [{"type": "heading", "text": "x"}]},
        header_source="\\fancyhead{X}",
        assets={"logo.pdf": "YmFzZTY0"},
    )

    body = json.loads(calls[0].content)
    assert body == {
        "template": "_block",
        "data": {"body": [{"type": "heading", "text": "x"}]},
        "header_source": "\\fancyhead{X}",
        "footer_source": None,
        "assets": {"logo.pdf": "YmFzZTY0"},
    }


def test_a_call_without_a_bundle_sends_null_and_an_empty_map(upstream):
    calls = upstream(answering(200, content=b"%PDF"))

    render_pdf("_block", {"body": []})

    body = json.loads(calls[0].content)
    assert body["header_source"] is None
    assert body["footer_source"] is None
    assert body["assets"] == {}


@pytest.mark.parametrize("status", [400, 500, 503])
def test_documented_statuses_pass_through(upstream, status):
    detail = {"type": "input_error", "message": "no", "path": ["body", 1]}
    upstream(answering(status, json={"detail": detail}))

    with pytest.raises(RenderUpstreamError) as excinfo:
        render_pdf("_block", {})

    assert excinfo.value.status_code == status
    assert excinfo.value.detail == detail


def test_retry_after_is_forwarded(upstream):
    upstream(
        answering(
            503,
            json={"detail": {"type": "overloaded", "message": "busy"}},
            headers={"Retry-After": "5"},
        )
    )

    with pytest.raises(RenderUpstreamError) as excinfo:
        render_pdf("_block", {})

    assert excinfo.value.headers == {"Retry-After": "5"}


def test_no_other_upstream_headers_are_forwarded(upstream):
    upstream(
        answering(
            400,
            json={"detail": {"type": "input_error", "message": "no"}},
            headers={"X-Render-Host": "render-1", "Server": "uvicorn"},
        )
    )

    with pytest.raises(RenderUpstreamError) as excinfo:
        render_pdf("_block", {})

    assert excinfo.value.headers is None


def assert_unavailable(excinfo):
    error = excinfo.value
    assert error.status_code == 502
    assert error.detail["type"] == "render_unavailable"
    # Neither the internal hostname nor the exception text leaks out.
    assert "render:8000" not in error.detail["message"]
    assert "http" not in error.detail["message"]


@pytest.mark.parametrize(
    "handler",
    [
        # A pydantic 422 from the render service: the backend built a body
        # the service could not parse. That is a bug here, not the caller's.
        answering(422, json={"detail": [{"loc": ["body", "template"]}]}),
        # An unexpected status, however well-formed the body.
        answering(418, json={"detail": {"type": "teapot", "message": "no"}}),
        # A proxy or a crash between the two services.
        answering(502, html="<html>Bad Gateway</html>"),
        # A documented status carrying an undocumented body.
        answering(500, content=b"not json at all"),
        answering(400, json={"detail": "just a string"}),
        answering(400, json={"detail": {"message": "no type field"}}),
        answering(400, json=["not an object"]),
    ],
    ids=[
        "422-pydantic",
        "unexpected-status",
        "html-body",
        "invalid-json",
        "detail-not-an-object",
        "detail-without-type",
        "body-not-an-object",
    ],
)
def test_unusable_answers_become_502(upstream, handler):
    upstream(handler)

    with pytest.raises(RenderUpstreamError) as excinfo:
        render_pdf("_block", {})

    assert_unavailable(excinfo)


@pytest.mark.parametrize(
    "exc",
    [
        httpx.ConnectError("connection refused"),
        httpx.ReadTimeout("timed out reading from http://render:8000"),
        httpx.ConnectTimeout("timed out connecting"),
        httpx.RemoteProtocolError("server disconnected"),
    ],
    ids=["connect-error", "read-timeout", "connect-timeout", "protocol-error"],
)
def test_transport_failures_become_502(upstream, exc):
    def raiser(request):
        raise exc

    upstream(raiser)

    with pytest.raises(RenderUpstreamError) as excinfo:
        render_pdf("_block", {})

    assert_unavailable(excinfo)


def test_the_timeout_budget_stays_under_the_proxy():
    """Worst case has to leave the proxy room to receive a real answer.

    Caddy waits 180 s for a response header (infra/Caddyfile); connect +
    write + read is what this side can spend before giving up.
    """
    timeout = render_client.TIMEOUT
    assert (timeout.connect, timeout.write, timeout.read) == (5.0, 30.0, 130.0)
    assert timeout.connect + timeout.write + timeout.read < 180
