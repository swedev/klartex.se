# App image for the klartex.se backend — the heavy TeX Live layers live in
# the base image ghcr.io/swedev/klartex-se-base, built from
# backend/Dockerfile.base by .github/workflows/backend-base.yml. Only the
# venv and the app source are built here, so a release build takes a
# couple of minutes instead of rebuilding ~7 GB under QEMU.
#
# Bumping the base: change backend/Dockerfile.base and merge — the base
# workflow publishes a new tag — then update the FROM pin below in a
# separate PR. The pin carries both tag (readability) and manifest digest
# (immutability); never point at a moving reference.
FROM ghcr.io/swedev/klartex-se-base:20260828-1@sha256:640992b132b9880eb0f801b81ac5f30ea64190243fa8900fbfda098cb158562b

WORKDIR /app
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir \
        klartex==0.14.0 \
        "fastapi>=0.115.0" \
        "uvicorn[standard]>=0.34.0" \
        "python-multipart>=0.0.20"

COPY src/ ./src/

ENV PATH="/usr/local/texlive-bin:/opt/venv/bin:$PATH" \
    PYTHONPATH="/app/src" \
    PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "klartex_se.main:app", "--host", "0.0.0.0", "--port", "8000"]
