# App image for the klartex.se backend — policy, discovery, the page-template
# registry and the whole public /api surface. It never compiles anything, so
# it carries no TeX Live: LaTeX is compiled by the render service, which is
# built on the TeX base and released on its own version series. That is what
# keeps a product release down to a few tens of megabytes.
FROM python:3.12-slim

WORKDIR /app

# Installed from pyproject.toml so the klartex pin lives in exactly one place
# per service — CI checks that this service and the render service pin the
# same core.
COPY pyproject.toml ./
COPY src/ ./src/
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir .

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

EXPOSE 8000

# The slim image carries no curl, so the probe is a Python one-liner. The
# compose file repeats this command: a healthcheck: block there overrides
# the one baked in here.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health', timeout=3)" || exit 1

CMD ["uvicorn", "klartex_se.main:app", "--host", "0.0.0.0", "--port", "8000"]
