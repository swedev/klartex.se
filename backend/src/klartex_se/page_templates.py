r"""Page-template registry — named bundles of .tex.jinja + assets.

Stored on disk at PAGE_TEMPLATES_DIR (default /data/page-templates). Each
bundle is a directory:

    <name>/
        page_template.tex.jinja      # the template source
        logo.pdf, font.ttf, ...      # arbitrary assets, available to xelatex
        _metadata.json               # created_at, description, asset_names

Names are restricted to [a-z0-9-]{1,64} so they're safe as path segments
and URL-friendly. Asset filenames must not contain path separators or
leading dots.

Asset resolution
----------------
Nothing here compiles. `load_bundle_payload` reads a bundle into a source
string plus base64 assets, and the render service writes those to a
temporary directory of its own, which it puts on TEXINPUTS and runs
xelatex in. The directory a template's references resolve against is
therefore a copy, never this one. Two reference forms behave differently
inside the .tex.jinja:

* Bare filename (`\includegraphics{logo.pdf}`) — resolved via TEXINPUTS:
  the bundle's files first, the render process cwd as fallback.
* Explicit relative (`\includegraphics{./logo.pdf}`) — Kpathsea never
  consults TEXINPUTS for these, so it resolves against the bundle's files
  only, with no cwd fallback.

When a name exists both in the bundle and in the render process cwd, the
bundle's copy wins. Parent-relative references are out of contract: asset
filenames carry no path separators, so no bundle can create that layout
through the API, and the render service rejects such a name outright.

Built-in templates
------------------
Alongside the registry, `builtin/<name>/` inside this package holds the
templates that ship with the backend: a `page_template.json` carrying the
slots in klartex's object form plus the asset files it references. They
resolve by name like bundles and appear in the listing, but they are not
bundles: they carry no `.tex.jinja`, they cannot be created, replaced or
deleted through the API, and their names are reserved so no bundle can
shadow them.

Forward-compat note: once orgs+auth land (fas 5), this layout migrates to
/data/orgs/<org>/page-templates/<name>/. The same internal API stays.
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path

# Limits — protect against runaway uploads. Soft enough for any realistic
# org branding (logo a few hundred KB, template a few KB).
MAX_TEMPLATE_BYTES = 1 * 1024 * 1024        # 1 MB
MAX_ASSET_BYTES = 5 * 1024 * 1024           # 5 MB per file
MAX_ASSETS = 10
TEMPLATE_FILENAME = "page_template.tex.jinja"
METADATA_FILENAME = "_metadata.json"

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
ASSET_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class PageTemplateError(ValueError):
    """User-facing validation error (mapped to 400 by the route layer)."""


class PageTemplateExists(PageTemplateError):
    """Tried to create a name that already exists without overwrite=true."""


class PageTemplateNotFound(KeyError):
    """No registered template with that name."""


class PageTemplateReserved(PageTemplateError):
    """The name belongs to a built-in template, which the API cannot write."""


BUILTIN_DIR = Path(__file__).parent / "builtin"
BUILTIN_FILENAME = "page_template.json"


def builtin_names() -> list[str]:
    """Names of the templates that ship with the backend, sorted."""
    if not BUILTIN_DIR.exists():
        return []
    return sorted(
        entry.name
        for entry in BUILTIN_DIR.iterdir()
        if entry.is_dir() and (entry / BUILTIN_FILENAME).exists()
    )


def is_builtin(name: str) -> bool:
    return name in builtin_names()


def _builtin_definition(name: str) -> dict:
    return json.loads(
        (BUILTIN_DIR / name / BUILTIN_FILENAME).read_text(encoding="utf-8")
    )


def _builtin_metadata(name: str) -> dict:
    definition = _builtin_definition(name)
    asset_names = sorted(
        entry.name
        for entry in (BUILTIN_DIR / name).iterdir()
        if entry.is_file() and entry.name != BUILTIN_FILENAME
    )
    return {
        "name": name,
        "description": definition.get("description"),
        "builtin": True,
        "asset_names": asset_names,
    }


def load_builtin(name: str) -> tuple[dict, dict, dict[str, str]]:
    """Return a built-in as (page-template slots, body fields, assets).

    The slots are klartex's object form and go under `data.page_template`.
    The body fields (`body_logo`) are the recipe-level logo settings for
    templates whose schema takes a body logo; the render endpoint decides
    whether they apply. Assets are base64 by filename, the form the render
    service takes.
    """
    if not is_builtin(name):
        raise PageTemplateNotFound(name)
    definition = _builtin_definition(name)
    assets = {
        entry.name: base64.b64encode(entry.read_bytes()).decode()
        for entry in (BUILTIN_DIR / name).iterdir()
        if entry.is_file() and entry.name != BUILTIN_FILENAME
    }
    return definition["page_template"], definition.get("body_logo") or {}, assets


def _root() -> Path:
    return Path(os.environ.get("PAGE_TEMPLATES_DIR", "/data/page-templates"))


def _bundle_dir(name: str) -> Path:
    if not NAME_RE.match(name):
        raise PageTemplateError(
            f"Invalid name {name!r}; must match [a-z0-9][a-z0-9-]{{0,63}}"
        )
    return _root() / name


def list_bundles() -> list[dict]:
    """Return all page templates as metadata dicts, built-ins first."""
    out = [_builtin_metadata(name) for name in builtin_names()]
    root = _root()
    if not root.exists():
        return out
    for entry in sorted(root.iterdir()):
        if entry.is_dir() and (entry / METADATA_FILENAME).exists():
            out.append(_load_metadata(entry))
    return out


def get_bundle(name: str) -> dict:
    """Return metadata for a single template. Raises PageTemplateNotFound."""
    if is_builtin(name):
        return _builtin_metadata(name)
    d = _bundle_dir(name)
    if not d.exists() or not (d / METADATA_FILENAME).exists():
        raise PageTemplateNotFound(name)
    return _load_metadata(d)


def get_bundle_path(name: str) -> Path:
    """Return the directory path, proving the bundle exists.

    The render endpoint calls this to settle existence as policy — an
    unregistered name is a 400 — before `load_bundle_payload` reads the
    contents inside the in-flight semaphore.
    """
    d = _bundle_dir(name)
    if not d.exists() or not (d / METADATA_FILENAME).exists():
        raise PageTemplateNotFound(name)
    return d


def load_bundle_payload(name: str) -> tuple[str, dict[str, str]]:
    """Return a bundle as (template source, assets as base64 by filename).

    This is the form the render service takes: it has no volume and no
    knowledge of the registry, so a bundle travels inline with the call.

    Raises PageTemplateNotFound when the bundle is gone — it can disappear
    between a lookup and this read — and PageTemplateError when it is
    there but unusable: a template source that is not UTF-8, metadata that
    is not readable JSON, or an asset the metadata lists but disk does not
    have. Those describe a broken bundle rather than a broken call, but the
    caller can only report them to whoever asked for it.
    """
    d = get_bundle_path(name)

    try:
        source = (d / TEMPLATE_FILENAME).read_text(encoding="utf-8")
    except FileNotFoundError as e:
        raise PageTemplateNotFound(name) from e
    except UnicodeDecodeError as e:
        raise PageTemplateError(
            f"Page template {name!r}: {TEMPLATE_FILENAME} is not valid UTF-8"
        ) from e

    try:
        metadata = _load_metadata(d)
    except FileNotFoundError as e:
        # Deleted between get_bundle_path and here.
        raise PageTemplateNotFound(name) from e
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as e:
        # Not JSON, not UTF-8, or unreadable — all the same on-disk damage
        # the asset-name check below also guards against.
        raise PageTemplateError(
            f"Page template {name!r}: {METADATA_FILENAME} is unreadable"
        ) from e

    assets: dict[str, str] = {}
    for filename in metadata.get("asset_names") or []:
        # save_bundle enforces this on the way in; enforced again on the way
        # out so a metadata file edited on disk cannot turn a listed asset
        # name into a path that leaves the bundle.
        if not ASSET_NAME_RE.match(filename):
            raise PageTemplateError(
                f"Page template {name!r}: invalid asset filename {filename!r}"
            )
        try:
            raw = (d / filename).read_bytes()
        except OSError as e:
            raise PageTemplateError(
                f"Page template {name!r}: asset {filename!r} is missing"
            ) from e
        assets[filename] = base64.b64encode(raw).decode()

    return source, assets


def save_bundle(
    name: str,
    template_b64: str,
    assets_b64: dict[str, str],
    description: str | None = None,
    overwrite: bool = False,
) -> dict:
    """Create or replace a bundle. Returns the saved metadata."""
    d = _bundle_dir(name)
    if is_builtin(name):
        raise PageTemplateReserved(
            f"Page template {name!r} is built in and cannot be replaced"
        )
    if d.exists() and not overwrite:
        raise PageTemplateExists(
            f"Page template {name!r} already exists; set overwrite=true to replace"
        )

    template_bytes = _decode("template", template_b64, MAX_TEMPLATE_BYTES)

    if len(assets_b64) > MAX_ASSETS:
        raise PageTemplateError(
            f"Too many assets ({len(assets_b64)}); max is {MAX_ASSETS}"
        )

    decoded_assets: dict[str, bytes] = {}
    for filename, b64 in assets_b64.items():
        if not ASSET_NAME_RE.match(filename):
            raise PageTemplateError(
                f"Invalid asset filename {filename!r}; "
                "must match [A-Za-z0-9][A-Za-z0-9._-]+"
            )
        decoded_assets[filename] = _decode(
            f"asset {filename!r}", b64, MAX_ASSET_BYTES
        )

    # Atomic-ish write: stage to .tmp, swap. Avoids leaving a half-written
    # bundle if something goes wrong mid-write.
    staging = d.with_suffix(".tmp")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    try:
        (staging / TEMPLATE_FILENAME).write_bytes(template_bytes)
        for filename, content in decoded_assets.items():
            (staging / filename).write_bytes(content)
        metadata = {
            "name": name,
            "description": description,
            "created_at": _now_iso(),
            "asset_names": sorted(decoded_assets.keys()),
        }
        # Preserve created_at on overwrite — only refresh updated_at.
        if d.exists():
            try:
                prev = _load_metadata(d)
                metadata["created_at"] = prev.get("created_at", metadata["created_at"])
                metadata["updated_at"] = _now_iso()
            except Exception:
                pass
        (staging / METADATA_FILENAME).write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False)
        )

        if d.exists():
            shutil.rmtree(d)
        staging.rename(d)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        raise

    return metadata


def delete_bundle(name: str) -> None:
    d = _bundle_dir(name)
    if is_builtin(name):
        raise PageTemplateReserved(
            f"Page template {name!r} is built in and cannot be deleted"
        )
    if not d.exists():
        raise PageTemplateNotFound(name)
    shutil.rmtree(d)


# --- helpers ----------------------------------------------------------------

def _decode(label: str, b64: str, max_bytes: int) -> bytes:
    try:
        raw = base64.b64decode(b64, validate=True)
    except (ValueError, TypeError) as e:
        raise PageTemplateError(f"{label}: invalid base64: {e}") from e
    if len(raw) > max_bytes:
        raise PageTemplateError(
            f"{label}: {len(raw)} bytes exceeds limit {max_bytes}"
        )
    return raw


def _load_metadata(bundle_dir: Path) -> dict:
    return json.loads((bundle_dir / METADATA_FILENAME).read_text())


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
