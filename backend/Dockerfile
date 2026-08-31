# App image for the klartex.se backend — policy, discovery, the page-template
# registry and the whole public /api surface. It never compiles anything, so
# it carries no TeX Live: LaTeX is compiled by ghcr.io/swedev/klartex-render,
# which the klartex core builds and publishes with every release. That is what
# keeps a product release down to a few tens of megabytes.
FROM python:3.12-slim

WORKDIR /app

# Installed from pyproject.toml so the klartex pin lives in exactly one
# place — infra/.env.example derives KLARTEX_VERSION from it, and CI fails
# when the two disagree.
COPY pyproject.toml ./
COPY src/ ./src/
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir .

# The migration environment travels in the image, not just the source tree:
# the deploy preflights with `docker compose run --rm backend alembic current`
# and migrates with `alembic upgrade head`, both against the image that is
# about to serve. WORKDIR is /app, where alembic.ini sits, so the bare
# `alembic` command resolves its config without -c.
COPY alembic.ini ./
COPY migrations/ ./migrations/

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

EXPOSE 8000

# The slim image carries no curl, so the probe is a Python one-liner. The
# compose file repeats this command: a healthcheck: block there overrides
# the one baked in here.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health', timeout=3)" || exit 1

CMD ["uvicorn", "klartex_se.main:app", "--host", "0.0.0.0", "--port", "8000"]
