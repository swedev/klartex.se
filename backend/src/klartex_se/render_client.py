"""HTTP client for the render service — the only place LaTeX compilation goes.

The render service is the klartex core's own artifact: it is the process
that calls `klartex.render()`, so it is where the core's messages are
interpreted and where the error shapes are decided. This module's job is
therefore narrow. It sends the request, hands back the PDF, and translates
everything else into a `RenderUpstreamError` the endpoint can turn into an
HTTP response:

* a 400/500/503 carrying a well-formed `detail` object passes through with
  its status, its detail and its `Retry-After` untouched, so a client sees
  exactly what it saw before the split;
* anything else — an unexpected status, HTML from a proxy, a body that is
  not the agreed shape, a connection failure, a timeout — becomes `502
  render_unavailable`. The upstream answer is logged server-side; the
  client is told only that the service did not answer, without the internal
  hostname.

A 200 counts as an answer only when the body actually opens with `%PDF`.
An intermediary that answers a POST with its own 200 — a captive portal, a
login page, an ingress error rendered as HTML — is otherwise indistinguishable
from the renderer here, and the bytes would reach the caller labelled
`application/pdf`.

The time budget is explicit and has to stay under the proxy's. The core
runs xelatex twice with a 60 s timeout each, so a legitimate render can take
two minutes: connect 5 + write 30 + read 130 is 165 s worst case, and Caddy
waits 180 s for a response header (see infra/Caddyfile).
"""

import logging
import os
import threading

import httpx

log = logging.getLogger(__name__)

RENDER_URL = os.environ.get("RENDER_URL", "http://render:8000")

TIMEOUT = httpx.Timeout(connect=5.0, read=130.0, write=30.0, pool=5.0)

# Statuses the render service is allowed to speak on its own behalf. Every
# other status means the answer did not come from a working renderer.
PASSTHROUGH_STATUSES = frozenset({400, 500, 503})

UNAVAILABLE_DETAIL = {
    "type": "render_unavailable",
    "message": "The render service did not answer. Retry in a few seconds.",
}

_client_instance: httpx.Client | None = None
_client_lock = threading.Lock()


class RenderUpstreamError(Exception):
    """A render call that did not produce a PDF, as an HTTP answer.

    `status_code`, `detail` and `headers` are what the endpoint should
    reply with — either the render service's own answer or the 502 this
    module substitutes for one it cannot trust.
    """

    def __init__(
        self,
        status_code: int,
        detail: dict,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(f"render service answered {status_code}")
        self.status_code = status_code
        self.detail = detail
        self.headers = headers


def _client() -> httpx.Client:
    """Return the shared HTTP client.

    A module-level function rather than a module-level object so tests can
    replace the transport — tests/test_contract.py substitutes a TestClient
    that drives the core's render app in-process.
    """
    global _client_instance
    if _client_instance is None:
        with _client_lock:
            if _client_instance is None:
                _client_instance = httpx.Client(timeout=TIMEOUT)
    return _client_instance


def _upstream_detail(response: httpx.Response) -> dict | None:
    """Return the upstream `detail` object, or None if it is not one.

    Only a body of the agreed shape — `{"detail": {"type": ..., "message":
    ...}}` — may reach the client. Anything else, from an HTML error page
    to a body that merely looks close enough, falls through to the 502.
    """
    try:
        payload = response.json()
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    detail = payload.get("detail")
    if not isinstance(detail, dict):
        return None
    if not isinstance(detail.get("type"), str):
        return None
    if not isinstance(detail.get("message"), str):
        return None
    return detail


def render_pdf(
    template: str,
    data: dict,
    header_source: str | None = None,
    footer_source: str | None = None,
    assets: dict[str, str] | None = None,
) -> bytes:
    """Compile a document via the render service and return the PDF bytes.

    Raises RenderUpstreamError for every outcome that is not a PDF.
    """
    payload = {
        "template": template,
        "data": data,
        "header_source": header_source,
        "footer_source": footer_source,
        "assets": assets or {},
    }

    try:
        response = _client().post(f"{RENDER_URL}/render", json=payload)
    except httpx.TransportError as e:
        log.warning("render service unreachable: %s: %s", type(e).__name__, e)
        raise RenderUpstreamError(502, dict(UNAVAILABLE_DETAIL)) from e

    # A truncated PDF still opens with the signature, so this does not
    # promise a readable document — it separates a render from an answer
    # that never came from a renderer at all.
    if response.status_code == 200 and response.content[:4] == b"%PDF":
        return response.content

    if response.status_code in PASSTHROUGH_STATUSES:
        detail = _upstream_detail(response)
        if detail is not None:
            headers = {}
            retry_after = response.headers.get("Retry-After")
            if retry_after is not None:
                headers["Retry-After"] = retry_after
            raise RenderUpstreamError(
                response.status_code, detail, headers or None
            )

    log.warning(
        "unusable answer from the render service: HTTP %s (%s): %.200s",
        response.status_code,
        response.headers.get("Content-Type", "no content type"),
        response.text,
    )
    raise RenderUpstreamError(502, dict(UNAVAILABLE_DETAIL))
