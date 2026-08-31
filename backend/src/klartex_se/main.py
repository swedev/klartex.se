"""FastAPI app entrypoint. Mounts the account, discovery, registry and
render routers under /api."""

import importlib.metadata

from fastapi import APIRouter, FastAPI

from klartex_se import __version__
from klartex_se.accounts import router as accounts_router
from klartex_se.discovery import router as discovery_router
from klartex_se.page_template_router import router as page_template_router
from klartex_se.render import router as render_router

app = FastAPI(
    title="klartex.se backend",
    description="Wraps klartex (library) for the klartex.se webapp.",
    version=__version__,
    docs_url=None,
    openapi_url="/api/openapi.json",
    redoc_url=None,
)

# Every route lives under /api: Caddy proxies /api/* to this app on the same
# origin as the webapp bundle, and Vite proxies /api in dev, so paths are
# identical everywhere. Defining the prefix once keeps a new router from
# missing it.
api_router = APIRouter(prefix="/api")


@api_router.get("/health")
def health() -> dict:
    """Liveness probe — used by Docker healthcheck + uptime monitoring.

    `klartex` is the installed core version. Discovery schemas come from
    it and the renderer from the core inside the render service, which
    reports the same field; a deploy compares the two health answers and
    fails if they differ.
    """
    return {
        "status": "ok",
        "version": __version__,
        "klartex": importlib.metadata.version("klartex"),
    }


api_router.include_router(accounts_router)
api_router.include_router(discovery_router)
api_router.include_router(page_template_router)
api_router.include_router(render_router)

app.include_router(api_router)
