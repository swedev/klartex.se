# backend/

FastAPI-app som importerar `klartex` (PyPI) som library och exponerar HTTP-API:t som klartex.se frontend använder.

Ersätter kärnans utfasade `klartex serve` (borttagen i klartex v0.11.0). HTTP-yta hör hemma här, där webbappens andra beslut (auth, persistens, asset-hantering) också bor.

## Endpoints

| Metod & path | Vad |
|--------------|-----|
| `GET /health` | Liveness — används av Docker healthcheck |
| `GET /templates` | Lista mallar (block-engine + recipe) |
| `GET /templates/{name}/schema` | JSON Schema för en mall |
| `GET /blocks` | Lista block-engine-blocktyper |
| `GET /blocks/{name}/schema` | JSON Schema för en blocktyp |
| `POST /render` | JSON in, PDF out |

Multipart-varianten `/render-with-assets` (logo + `.tex.jinja`-upload) tillkommer i nästa iteration.

## Lokal utveckling

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Kör servern
uvicorn klartex_se.main:app --reload --port 8000

# Smoke-test
curl http://localhost:8000/templates | jq '.[].name'
curl -X POST http://localhost:8000/render \
  -H "Content-Type: application/json" \
  -d '{"template":"_block","data":{"lang":"sv","body":[{"type":"heading","text":"Test"}]}}' \
  -o /tmp/test.pdf
```

Tester (`xelatex` behövs för render-tester):

```bash
pytest
pytest -k "not render"   # bara discovery-tester (snabbt, ingen xelatex)
```

## Docker

```bash
docker build -t klartex-se-backend:dev .
docker run --rm -p 8000:8000 klartex-se-backend:dev
```

## Deploy

Bygg + push sker via `.github/workflows/backend.yml` på varje merge till `main` som rör `backend/`. Bygger multi-arch (amd64 + arm64) till `ghcr.io/swedev/klartex-se-backend`.

För produktion: bumpa `version` i `pyproject.toml`, merga, vänta på workflow, uppdatera `KLARTEX_SE_BACKEND_VERSION` i `infra/.env`, kör `./deploy/deploy.sh`.
