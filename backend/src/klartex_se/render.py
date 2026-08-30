"""Render endpoint: JSON in, PDF out.

Policy lives here; compilation does not. The endpoint decides what the
caller is allowed to render, resolves the page template against the
registry, and proxies the work to the render service, which is the only
process that runs xelatex.

Three modes for the page template:

1. `page_template: "vkf"` — name of a bundle registered via
   /api/page-templates. The bundle's template source and assets travel
   inline with the render call.
2. `page_template: "formal" | "clean" | "none"` — klartex built-in,
   passed through as data["page_template"].
3. `page_template: null` — whichever default klartex picks
   (currently "none").

Error shapes come from the render service and pass through unchanged, so
`detail.type`, `detail.path` and `Retry-After` mean what they have always
meant. The one answer this layer adds is `502 render_unavailable`, when
the render service cannot be reached or does not answer in time.

The endpoint is tier-aware. Anonymous callers render every block except
`latex`, which passes raw LaTeX to the compiler and answers `403
token_required`; a valid API token unlocks the full block surface.
"""

import logging
import threading

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from klartex_se.auth import TOKEN_HOWTO, Tier, render_tier
from klartex_se.page_templates import (
    PageTemplateError,
    PageTemplateNotFound,
    get_bundle_path,
    load_bundle_payload,
)
from klartex_se.render_client import RenderUpstreamError, render_pdf

log = logging.getLogger(__name__)

router = APIRouter(tags=["render"])

# klartex built-in page-template names. Passed through as data["page_template"];
# bundle lookup is skipped for these.
BUILTIN_PAGE_TEMPLATES = {"formal", "clean", "none"}

# Cap on render calls in flight towards the render service. The same number
# as the render service's own cap: further calls could only wait for a 503
# from it, and two is the ceiling on how many bundle payloads — up to ~68 MB
# of base64 each, plus the JSON copies of them — are built here at once.
MAX_INFLIGHT_RENDERS = 2

_inflight_slots = threading.BoundedSemaphore(MAX_INFLIGHT_RENDERS)


def _child_block_lists(
    block: dict, path: list[str | int]
) -> list[tuple[object, list[str | int]]]:
    """Return the nested block lists of `block` as (blocks, path) pairs.

    Mirrors `klartex.renderer._child_block_lists` — the core's single
    source of truth for which block types nest other blocks — without
    importing a private name into production code. A block type absent
    here carries no blocks, so its remaining properties are ordinary
    data. tests/test_render.py pins this against the core, so a carrier
    added there fails a test rather than silently opening the gate.
    """
    btype = block.get("type")
    if btype == "list":
        return [
            (item.get("content"), path + ["items", i, "content"])
            for i, item in enumerate(block.get("items") or [])
            if isinstance(item, dict)
        ]
    if btype == "columns":
        return [
            (column, path + ["items", i])
            for i, column in enumerate(block.get("items") or [])
            if isinstance(column, list)
        ]
    if btype == "clause":
        return [(block.get("content"), path + ["content"])]
    return []


def find_latex_block(body: object) -> list[str | int] | None:
    """Locate the first `latex` block in a `_block` body.

    Returns the path to the first block carrying `"type": "latex"` — a
    `["body", 0, "items", 1, 0]` list, the same shape `detail.path`
    already uses — in document order, or None when there is none.

    Only the positions the block engine actually reads as blocks are
    visited: the top-level `body` list and, from there, the carriers in
    `_child_block_lists`. Ordinary data is never mistaken for a block,
    so a `parties` block whose `party1` happens to carry
    `"type": "latex"` renders anonymously, exactly as the core renders
    it. Iterative, since deeply nested request JSON must not be able to
    raise RecursionError.
    """
    stack: list[tuple[object, list[str | int]]] = []

    def push(blocks: object, path: list[str | int]) -> None:
        if isinstance(blocks, list):
            stack.extend(
                (block, path + [i]) for i, block in reversed(list(enumerate(blocks)))
            )

    push(body, ["body"])
    while stack:
        block, path = stack.pop()
        if not isinstance(block, dict):
            continue
        if block.get("type") == "latex":
            return path
        for blocks, child_path in reversed(_child_block_lists(block, path)):
            push(blocks, child_path)
    return None


class RenderRequest(BaseModel):
    template: str = Field(
        ...,
        description="Template name. Use `_block` for block-engine path.",
        examples=["_block", "protokoll", "faktura"],
    )
    data: dict = Field(..., description="Template data; validated against schema.")
    page_template: str | None = Field(
        None,
        description=(
            "Either a registered bundle name (see /api/page-templates) or "
            "one of the klartex built-ins: formal, clean, none. If null, "
            "klartex picks its default."
        ),
        examples=["vkf", "formal"],
    )


def _unknown_page_template(name: str) -> HTTPException:
    return HTTPException(
        400,
        detail={
            "type": "unknown_page_template",
            "message": (
                f"Page template {name!r} is not registered and not a built-in."
            ),
        },
    )


@router.post(
    "/render",
    response_class=Response,
    responses={
        200: {"content": {"application/pdf": {}}},
        400: {
            "description": (
                "Schema validation or input failure. `detail.type` is one "
                "of `validation_error`, `input_error`, "
                "`unknown_page_template`; `detail.path` locates the "
                "failing node when one can be identified."
            )
        },
        401: {
            "description": (
                "An Authorization header was presented but does not carry "
                "a usable token. `detail.type` is `token_required` when "
                "the header lacks the `Bearer ` prefix and `invalid_token` "
                "when the token does not match. Neither body carries "
                "`path` or `block_type` — those belong to the 403."
            )
        },
        403: {
            "description": (
                "The request uses a block the anonymous tier may not "
                "render. `detail.type` is `token_required`, "
                "`detail.block_type` names the block and `detail.path` "
                "locates it."
            )
        },
        500: {"description": "xelatex failure"},
        502: {
            "description": (
                "The render service could not be reached, answered too "
                "slowly, or answered something unusable. `detail.type` is "
                "`render_unavailable` and the call is safe to retry."
            )
        },
        503: {
            "description": (
                "Either too many concurrent renders (`detail.type` is "
                "`overloaded`, raised here or by the render service) or a "
                "token was presented to an instance with none configured "
                "(`token_not_configured`)."
            )
        },
    },
)
def render(req: RenderRequest, tier: Tier = Depends(render_tier)) -> Response:
    """Render a template + data combination to a PDF."""
    if tier is Tier.ANONYMOUS and req.template == "_block":
        latex_path = find_latex_block(req.data.get("body"))
        if latex_path is not None:
            raise HTTPException(
                403,
                detail={
                    "type": "token_required",
                    "block_type": "latex",
                    "path": latex_path,
                    "message": (
                        "The 'latex' block passes raw LaTeX to the compiler "
                        f"and requires an API token. {TOKEN_HOWTO}"
                    ),
                },
            )

    data = req.data
    bundle: str | None = None

    if req.page_template:
        if req.page_template in BUILTIN_PAGE_TEMPLATES:
            # Klartex resolves this internally from data.page_template.
            data = {**data, "page_template": req.page_template}
        else:
            # Existence is policy and settled here; the bundle's contents
            # are read inside the semaphore, where the memory they take is
            # accounted for.
            try:
                get_bundle_path(req.page_template)
            except PageTemplateNotFound as e:
                raise _unknown_page_template(req.page_template) from e
            bundle = req.page_template

    if not _inflight_slots.acquire(blocking=False):
        raise HTTPException(
            status_code=503,
            detail={
                "type": "overloaded",
                "message": (
                    "Too many concurrent renders. Retry in a few seconds."
                ),
            },
            headers={"Retry-After": "5"},
        )

    try:
        page_template_source: str | None = None
        assets: dict[str, str] = {}
        if bundle is not None:
            try:
                page_template_source, assets = load_bundle_payload(bundle)
            except PageTemplateNotFound as e:
                raise _unknown_page_template(bundle) from e
            except PageTemplateError as e:
                raise HTTPException(
                    400,
                    detail={"type": "input_error", "message": str(e)},
                ) from e

        try:
            pdf_bytes = render_pdf(
                req.template,
                data,
                page_template_source=page_template_source,
                assets=assets,
            )
        except RenderUpstreamError as e:
            raise HTTPException(
                status_code=e.status_code, detail=e.detail, headers=e.headers
            ) from e
    finally:
        _inflight_slots.release()

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="document.pdf"'},
    )
