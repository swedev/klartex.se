"""HTTP routes for the page-template registry."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from klartex_se.auth import require_api_token
from klartex_se.page_templates import (
    PageTemplateError,
    PageTemplateExists,
    PageTemplateNotFound,
    delete_bundle,
    get_bundle,
    list_bundles,
    save_bundle,
)

router = APIRouter(prefix="/page-templates", tags=["page-templates"])


class CreateBundle(BaseModel):
    name: str = Field(
        ...,
        description="Bundle name (also URL segment). Lowercase, alphanumeric + dashes.",
        examples=["vkf", "insector-main"],
    )
    template: str = Field(..., description="Base64-encoded .tex.jinja content.")
    assets: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Filename → base64 bytes. Files become available to xelatex at "
            "render time via TEXINPUTS (e.g. logo.pdf for \\includegraphics)."
        ),
    )
    description: str | None = Field(
        None, description="Optional human-readable description."
    )
    overwrite: bool = Field(
        False,
        description="If true, replace an existing bundle with the same name.",
    )


@router.get("")
def list_() -> list[dict]:
    """List all registered page templates. Public."""
    return list_bundles()


@router.get("/{name}")
def get(name: str) -> dict:
    """Metadata for one bundle. Public."""
    try:
        return get_bundle(name)
    except PageTemplateNotFound as e:
        raise HTTPException(404, f"Page template {name!r} not found") from e


@router.post("", status_code=status.HTTP_201_CREATED)
def create(req: CreateBundle, _: None = Depends(require_api_token)) -> dict:
    """Create or replace a page-template bundle. Requires API_TOKEN."""
    try:
        return save_bundle(
            name=req.name,
            template_b64=req.template,
            assets_b64=req.assets,
            description=req.description,
            overwrite=req.overwrite,
        )
    except PageTemplateExists as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    except PageTemplateError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
def delete(name: str, _: None = Depends(require_api_token)) -> None:
    """Delete a bundle. Requires API_TOKEN."""
    try:
        delete_bundle(name)
    except PageTemplateNotFound as e:
        raise HTTPException(404, f"Page template {name!r} not found") from e
    except PageTemplateError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
