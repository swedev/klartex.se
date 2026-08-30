"""Render endpoint: JSON in, PDF out.

Wraps `klartex.render()`. Supports three modes for the page template:

1. `page_template: "vkf"` — name of a bundle registered via
   /api/page-templates. Server loads its tex.jinja + asset_dir.
2. `page_template: "formal" | "clean" | "none"` — klartex built-in,
   passed through as data["page_template"].
3. `page_template: null` — whichever default klartex picks
   (currently "none").

Validation errors and xelatex failures are mapped to HTTP responses with
structured detail the frontend can present. Schema violations and block
validation errors both carry `detail.path` — a
`["body", 1, "items", 0, "text"]` list addressing the failing node in the
submitted data — so a client can mark the offending block without parsing
`detail.message`.
"""

import logging
import re
import threading
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from jsonschema import ValidationError
from pydantic import BaseModel, Field

from klartex import render as klartex_render

from klartex_se.page_templates import (
    PageTemplateNotFound,
    TEMPLATE_FILENAME,
    get_bundle_path,
)

log = logging.getLogger(__name__)

router = APIRouter(tags=["render"])

# klartex built-in page-template names. Passed through as data["page_template"];
# bundle lookup is skipped for these.
BUILTIN_PAGE_TEMPLATES = {"formal", "clean", "none"}

# Cap on concurrent xelatex runs. FastAPI dispatches sync endpoints to a
# thread pool of ~40 threads, so without a cap that many xelatex processes
# can start at once. The value assumes a single uvicorn worker per
# container: additional workers or replicas multiply the effective cap.
MAX_CONCURRENT_RENDERS = 2

_render_slots = threading.BoundedSemaphore(MAX_CONCURRENT_RENDERS)

# Block position inside a klartex block-validation message, e.g. `body[1]`
# or `body[0].items[1][0]` for a block nested in a carrier block.
_BLOCK_POSITION = r"body(?:\[\d+\]|\.[a-z_]+)+"

# The three message forms `klartex.renderer._validate_blocks` raises as
# ValueError. Anchored on the full form rather than searching for
# `at body[...]`: in the unknown-type message the type name is caller
# supplied and may itself contain that substring. The greedy `'.*'` plus
# the `. Available: ` anchor therefore selects the last occurrence.
# A message form the core changes falls through to `None`; the endpoint
# tests in tests/test_render.py run against the real core and pin this.
_BLOCK_ERROR_RE = re.compile(
    rf"^(?:Block at (?P<a>{_BLOCK_POSITION}) is missing 'type'$"
    rf"|Unknown block type '.*' at (?P<b>{_BLOCK_POSITION})\. Available: "
    rf"|Invalid '[a-z_]+' block at (?P<c>{_BLOCK_POSITION}): )",
    re.DOTALL,
)


def _block_error_path(exc: ValueError) -> list[str | int] | None:
    """Locate the node a klartex block-validation error refers to.

    Returns the position as a `["body", 1, "items", 0, "text"]` list —
    the same shape `list(ValidationError.absolute_path)` gives for the
    schema-validation path — or None when the message carries no block
    position (unknown template, invalid asset_dir).
    """
    m = _BLOCK_ERROR_RE.match(str(exc))
    if m is None:
        return None
    where = m.group("a") or m.group("b") or m.group("c")
    path: list[str | int] = [
        int(part) if part.isdigit() else part
        for part in re.findall(r"\d+|[a-z_]+", where)
    ]
    # The wrapped jsonschema error, when present, locates the field
    # inside the block; appending it addresses the failing node itself.
    cause = exc.__cause__
    if isinstance(cause, ValidationError):
        path.extend(cause.absolute_path)
    return path


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
        500: {"description": "xelatex failure"},
        503: {"description": "Too many concurrent renders"},
    },
)
def render(req: RenderRequest) -> Response:
    """Render a template + data combination to a PDF."""
    page_template_source: str | None = None
    asset_dir: Path | None = None
    data = req.data

    if req.page_template:
        if req.page_template in BUILTIN_PAGE_TEMPLATES:
            # Klartex resolves this internally from data.page_template.
            data = {**data, "page_template": req.page_template}
        else:
            try:
                bundle_dir = get_bundle_path(req.page_template)
            except PageTemplateNotFound as e:
                raise HTTPException(
                    400,
                    detail={
                        "type": "unknown_page_template",
                        "message": (
                            f"Page template {req.page_template!r} is not "
                            "registered and not a built-in."
                        ),
                    },
                ) from e
            page_template_source = (bundle_dir / TEMPLATE_FILENAME).read_text()
            asset_dir = bundle_dir

    if not _render_slots.acquire(blocking=False):
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
        pdf_bytes = klartex_render(
            req.template,
            data,
            page_template_source=page_template_source,
            asset_dir=asset_dir,
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=400,
            detail={
                "type": "validation_error",
                "message": e.message,
                "path": list(e.absolute_path),
            },
        ) from e
    except ValueError as e:
        detail: dict = {"type": "input_error", "message": str(e)}
        path = _block_error_path(e)
        if path is not None:
            detail["path"] = path
        raise HTTPException(status_code=400, detail=detail) from e
    except RuntimeError as e:
        log.exception("klartex render failed for template=%s", req.template)
        raise HTTPException(
            status_code=500,
            detail={"type": "render_error", "message": str(e)},
        ) from e
    finally:
        _render_slots.release()

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="document.pdf"'},
    )
