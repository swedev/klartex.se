# App image for the klartex.se backend — the heavy TeX Live layers live in
# the base image ghcr.io/swedev/klartex-base, built from docker/Dockerfile.base
# in swedev/klartex by its base-image.yml, which runs the klartex test suite
# inside the freshly built amd64 image before pushing. Only the venv and the
# app source are built here, so a release build takes a couple of minutes
# instead of rebuilding ~7 GB under QEMU.
#
# Bumping the base: bump it in swedev/klartex and wait for its base-image.yml
# to publish, then copy the image reference
# ghcr.io/swedev/klartex-base:<tag>@<digest> from that run's step summary into
# the FROM line below, in a separate PR here. The pin carries both tag
# (readability) and manifest digest (immutability); never point at a moving
# reference.
FROM ghcr.io/swedev/klartex-base:20260828-3@sha256:b011056413d449bdc41b893ff1bd538a2be46d78d3794698eb134f45936d6ff2

WORKDIR /app
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir \
        klartex==0.15.0 \
        "fastapi>=0.115.0" \
        "uvicorn[standard]>=0.34.0" \
        "python-multipart>=0.0.20"

COPY src/ ./src/

ENV PATH="/usr/local/texlive-bin:/opt/venv/bin:$PATH" \
    PYTHONPATH="/app/src" \
    PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "klartex_se.main:app", "--host", "0.0.0.0", "--port", "8000"]
