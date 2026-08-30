"""Compile endpoint: JSON in, PDF out. The only place that runs xelatex.

`klartex.render()` needs its page-template source as a string and its
assets as a directory on disk. This service takes both inline — the
caller sends `page_template_source` plus `assets` as base64 — writes the
assets to a temporary directory for the duration of the call, and deletes
it afterwards. Nothing survives a request: no registry, no volume, no
knowledge of who asked.

Validation errors and xelatex failures are mapped to HTTP responses with
structured detail. Schema violations and block validation errors both
carry `detail.path` — a `["body", 1, "items", 0, "text"]` list addressing
the failing node in the submitted data — so the caller can pass it
straight through to its own client.
"""

import base64
import logging
import re
import tempfile
import threading
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from jsonschema import ValidationError
from pydantic import BaseModel, Field

from klartex import render as klartex_render

log = logging.getLogger(__name__)

router = APIRouter(tags=["render"])

# Limits mirror the page-template registry in klartex_se.page_templates:
# a bundle that the registry accepted must be renderable here.
MAX_TEMPLATE_BYTES = 1 * 1024 * 1024        # 1 MB
MAX_ASSET_BYTES = 5 * 1024 * 1024           # 5 MB per file
MAX_ASSETS = 10

# Same restriction the registry puts on stored filenames. Enforced again
# here so no caller — not even a faulty backend — can write outside the
# per-request temporary directory.
ASSET_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

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
        description="Template name. Use `_block` for the block-engine path.",
        examples=["_block", "protokoll", "faktura"],
    )
    data: dict = Field(..., description="Template data; validated against schema.")
    page_template_source: str | None = Field(
        None,
        description=(
            "Contents of the bundle's page_template.tex.jinja, or null for "
            "whichever page template `data` selects."
        ),
    )
    assets: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Bundle assets as base64, keyed by filename. Written to a "
            "temporary directory that is handed to xelatex and deleted "
            "when the render returns."
        ),
    )


def _input_error(message: str) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={"type": "input_error", "message": message},
    )


def _decode_assets(assets: dict[str, str]) -> dict[str, bytes]:
    """Validate filenames and sizes, returning the decoded asset bytes."""
    if len(assets) > MAX_ASSETS:
        raise _input_error(f"Too many assets ({len(assets)}); max is {MAX_ASSETS}")

    decoded: dict[str, bytes] = {}
    for filename, b64 in assets.items():
        if not ASSET_NAME_RE.match(filename):
            raise _input_error(
                f"Invalid asset filename {filename!r}; "
                "must match [A-Za-z0-9][A-Za-z0-9._-]+"
            )
        try:
            raw = base64.b64decode(b64, validate=True)
        except (ValueError, TypeError) as e:
            raise _input_error(f"asset {filename!r}: invalid base64: {e}") from e
        if len(raw) > MAX_ASSET_BYTES:
            raise _input_error(
                f"asset {filename!r}: {len(raw)} bytes exceeds limit "
                f"{MAX_ASSET_BYTES}"
            )
        decoded[filename] = raw
    return decoded


@router.post(
    "/render",
    response_class=Response,
    responses={
        200: {"content": {"application/pdf": {}}},
        400: {
            "description": (
                "Schema validation or input failure. `detail.type` is "
                "`validation_error` or `input_error`; `detail.path` "
                "locates the failing node when one can be identified."
            )
        },
        500: {"description": "xelatex failure (`detail.type` is `render_error`)"},
        503: {
            "description": (
                "Too many concurrent renders — `detail.type` is "
                "`overloaded` and `Retry-After` says when to come back."
            )
        },
    },
)
def render(req: RenderRequest) -> Response:
    """Compile a template + data combination to a PDF."""
    assets = _decode_assets(req.assets)

    if req.page_template_source is not None:
        source_bytes = len(req.page_template_source.encode())
        if source_bytes > MAX_TEMPLATE_BYTES:
            raise _input_error(
                f"page_template_source: {source_bytes} bytes exceeds limit "
                f"{MAX_TEMPLATE_BYTES}"
            )

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
        with tempfile.TemporaryDirectory(prefix="klartex-render-") as tmp:
            # asset_dir stays None unless the caller sent a bundle, so a
            # plain render resolves its inputs exactly as it does without
            # this service in front of it.
            asset_dir: Path | None = None
            if req.page_template_source is not None or assets:
                asset_dir = Path(tmp)
                for filename, content in assets.items():
                    (asset_dir / filename).write_bytes(content)

            pdf_bytes = klartex_render(
                req.template,
                req.data,
                page_template_source=req.page_template_source,
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

    return Response(content=pdf_bytes, media_type="application/pdf")
