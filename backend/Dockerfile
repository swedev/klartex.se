FROM texlive/texlive:latest-minimal AS base

# Python + XeLaTeX packages klartex needs at render time.
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv curl \
    && rm -rf /var/lib/apt/lists/*

RUN tlmgr install xetex fontspec fancyhdr geometry xcolor titlesec enumitem \
        lastpage hyperref parskip setspace etoolbox booktabs tabularx tools \
        collection-fontsrecommended

# Build wheel separately so dependency layer caches between source changes.
WORKDIR /app
COPY pyproject.toml ./
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir \
        klartex==0.11.0 \
        "fastapi>=0.115.0" \
        "uvicorn[standard]>=0.34.0" \
        "python-multipart>=0.0.20"

COPY src/ ./src/

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH="/app/src" \
    PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "klartex_se.main:app", "--host", "0.0.0.0", "--port", "8000"]
