"""Discovery endpoints: templates, blocks, and their schemas.

These are thin passthroughs over klartex's library APIs. The frontend uses
them to autogenerate forms and block-pickers without hardcoding klartex's
schema knowledge.
"""

from fastapi import APIRouter, HTTPException

from klartex.components import list_components
from klartex.renderer import get_registry

router = APIRouter(tags=["discovery"])


@router.get("/templates")
def templates() -> list[dict]:
    """List all available document templates."""
    return [
        {
            "name": name,
            "description": info.description,
            "type": "block-engine" if info.is_block_engine else "recipe",
        }
        for name, info in sorted(get_registry().items())
    ]


@router.get("/templates/{name}/schema")
def template_schema(name: str) -> dict:
    """JSON Schema for a single template — used by frontend to render forms."""
    registry = get_registry()
    if name not in registry:
        raise HTTPException(404, f"Unknown template: {name}")
    return registry[name].schema


@router.get("/blocks")
def blocks() -> list[dict]:
    """Block types available in the block engine (template = `_block`)."""
    return [
        {"name": name}
        for name, spec in sorted(list_components().items())
        if spec.block_schema_path is not None
    ]


@router.get("/blocks/{name}/schema")
def block_schema(name: str) -> dict:
    """JSON Schema for a single block type."""
    components = list_components()
    spec = components.get(name)
    if spec is None or spec.block_schema_path is None:
        raise HTTPException(404, f"Unknown block type: {name}")
    import json
    return json.loads(spec.block_schema_path.read_text())
