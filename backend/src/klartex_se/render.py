"""Render endpoint: JSON in, PDF out.

Wraps `klartex.render()`. Supports three modes for the page template:

1. `page_template: "vkf"` — name of a bundle registered via
   /page-templates. Server loads its tex.jinja + asset_dir.
2. `page_template: "formal" | "clean" | "none"` — klartex built-in,
   passed through as data["page_template"].
3. `page_template: null` — whichever default klartex picks
   (currently "none").

Validation errors and xelatex failures are mapped to HTTP responses with
structured detail the frontend can present.
"""

import logging
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
            "Either a registered bundle name (see /page-templates) or one of "
            "the klartex built-ins: formal, clean, none. If null, klartex "
            "picks its default."
        ),
        examples=["vkf", "formal"],
    )


@router.post(
    "/render",
    response_class=Response,
    responses={
        200: {"content": {"application/pdf": {}}},
        400: {"description": "Schema validation or input failure"},
        500: {"description": "xelatex failure"},
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
        raise HTTPException(
            status_code=400,
            detail={"type": "input_error", "message": str(e)},
        ) from e
    except RuntimeError as e:
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
