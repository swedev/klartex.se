# Full TeX Live image — has everything klartex might need (tcolorbox,
# tikzfill, siunitx, fontspec, …) pre-installed. ~7 GB image, but build
# time is ~5 min instead of ~50+ min (no tlmgr install step). On the
# cax11 server (40 GB disk) the size is irrelevant; iteration speed wins.
FROM texlive/texlive:latest

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv curl \
    && rm -rf /var/lib/apt/lists/*

# texlive/texlive sets PATH via /etc/profile (login shell). uvicorn runs
# non-interactive, so symlink the arch-specific bin dir to a stable path
# and add it to ENV PATH.
RUN ln -s "$(ls -d /usr/local/texlive/*/bin/* | head -1)" /usr/local/texlive-bin

WORKDIR /app
COPY pyproject.toml ./
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir \
        klartex==0.11.0 \
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
