"""Render endpoint: JSON in, PDF out.

Wraps `klartex.render()`. Validation errors and xelatex failures are mapped
to HTTP responses with structured detail the frontend can present.

Multipart variant (`/render-with-assets`) for page-template + logo upload
ships in a follow-up — not in fas 1 backend skelett.
"""

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from jsonschema import ValidationError
from pydantic import BaseModel, Field

from klartex import render as klartex_render

log = logging.getLogger(__name__)

router = APIRouter(tags=["render"])


class RenderRequest(BaseModel):
    template: str = Field(
        ...,
        description="Template name. Use `_block` for block-engine path.",
        examples=["_block", "protokoll", "faktura"],
    )
    data: dict = Field(..., description="Template data; validated against schema.")
    page_template_source: str | None = Field(
        None,
        description=(
            "Optional raw .tex.jinja content for the page template. When "
            "set, overrides any built-in page template referenced by data."
        ),
    )


@router.post(
    "/render",
    response_class=Response,
    responses={
        200: {"content": {"application/pdf": {}}},
        400: {"description": "Schema validation failed"},
        500: {"description": "xelatex failure"},
    },
)
def render(req: RenderRequest) -> Response:
    """Render a template + data combination to a PDF."""
    try:
        pdf_bytes = klartex_render(
            req.template,
            req.data,
            page_template_source=req.page_template_source,
        )
    except ValidationError as e:
        # JSON Schema validation — user-fixable. Surface the path so the
        # frontend can highlight the offending field.
        raise HTTPException(
            status_code=400,
            detail={
                "type": "validation_error",
                "message": e.message,
                "path": list(e.absolute_path),
            },
        ) from e
    except ValueError as e:
        # Unknown template name, malformed input klartex rejects before
        # schema validation, etc. Same family as validation_error from the
        # caller's perspective: it's an input problem.
        raise HTTPException(
            status_code=400,
            detail={"type": "input_error", "message": str(e)},
        ) from e
    except RuntimeError as e:
        # xelatex failure — log it server-side, return a user-safe summary.
        log.exception("klartex render failed for template=%s", req.template)
        raise HTTPException(
            status_code=500,
            detail={"type": "render_error", "message": str(e)},
        ) from e

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="document.pdf"'},
    )
