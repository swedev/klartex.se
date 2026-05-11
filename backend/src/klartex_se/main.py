"""FastAPI app entrypoint. Mounts discovery + render routers."""

from fastapi import FastAPI

from klartex_se import __version__
from klartex_se.discovery import router as discovery_router
from klartex_se.render import router as render_router

app = FastAPI(
    title="klartex.se backend",
    description="Wraps klartex (library) for the klartex.se webapp.",
    version=__version__,
)

app.include_router(discovery_router)
app.include_router(render_router)


@app.get("/health")
def health() -> dict:
    """Liveness probe — used by Docker healthcheck + uptime monitoring."""
    return {"status": "ok", "version": __version__}
