"""FastAPI app entrypoint for the render service.

Internal service: reachable only on the compose network, so the routes
carry no `/api` prefix and no schema is published. Two endpoints — a
health probe and the compile call.
"""

import importlib.metadata

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from klartex_render import __version__
from klartex_render.render import router as render_router

# Largest request the service will look at. The biggest bundle the
# page-template registry can hold is 10 assets of 5 MB plus a 1 MB
# template; base64 inflates that to ~68 MB, and the document data comes
# on top. Anything larger is rejected on the Content-Length header, before
# a byte of the body is read.
MAX_REQUEST_BYTES = 80 * 1024 * 1024

app = FastAPI(
    title="klartex.se render service",
    description="Stateless wrapper around klartex.render().",
    version=__version__,
    docs_url=None,
    openapi_url=None,
    redoc_url=None,
)


@app.middleware("http")
async def limit_request_size(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared = int(content_length)
        except ValueError:
            declared = None
        if declared is not None and declared > MAX_REQUEST_BYTES:
            return JSONResponse(
                status_code=413,
                content={
                    "detail": {
                        "type": "payload_too_large",
                        "message": (
                            f"Request body of {declared} bytes exceeds the "
                            f"limit of {MAX_REQUEST_BYTES} bytes."
                        ),
                    }
                },
            )
    return await call_next(request)


@app.get("/health")
def health() -> dict:
    """Liveness probe — used by the Docker healthcheck and by deploys.

    `klartex` is the installed core version. The backend compares it with
    its own after a deploy: discovery schemas and the renderer have to
    come from the same core.
    """
    return {
        "status": "ok",
        "version": __version__,
        "klartex": importlib.metadata.version("klartex"),
    }


app.include_router(render_router)
