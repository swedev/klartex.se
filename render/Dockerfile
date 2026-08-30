# Render-service image — the only image in this repo that carries TeX Live.
# The heavy layers live in the base image ghcr.io/swedev/klartex-base, built
# from docker/Dockerfile.base in swedev/klartex by its base-image.yml, which
# runs the klartex test suite inside the freshly built amd64 image before
# pushing. Only the venv and the app source are built here, so a release
# build takes a couple of minutes instead of rebuilding ~7 GB under QEMU.
#
# Bumping the base: bump it in swedev/klartex and wait for its base-image.yml
# to publish, then copy the image reference
# ghcr.io/swedev/klartex-base:<tag>@<digest> from that run's step summary into
# the FROM line below, in a separate PR here. The pin carries both tag
# (readability) and manifest digest (immutability); never point at a moving
# reference.
FROM ghcr.io/swedev/klartex-base:20260828-3@sha256:b011056413d449bdc41b893ff1bd538a2be46d78d3794698eb134f45936d6ff2

WORKDIR /app

# Installed from pyproject.toml so the klartex pin lives in exactly one place
# per service — CI checks that this service and the backend pin the same core.
COPY pyproject.toml ./
COPY src/ ./src/
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir .

ENV PATH="/usr/local/texlive-bin:/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "klartex_render.main:app", "--host", "0.0.0.0", "--port", "8000"]
