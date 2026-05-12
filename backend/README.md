# backend/

FastAPI-app som importerar `klartex` (PyPI) som library och exponerar HTTP-API:t som klartex.se frontend använder.

Ersätter kärnans utfasade `klartex serve` (borttagen i klartex v0.11.0). HTTP-yta hör hemma här, där webbappens andra beslut (auth, persistens, asset-hantering) också bor.

## Endpoints

| Metod & path | Auth | Vad |
|--------------|------|-----|
| `GET /health` | — | Liveness — används av Docker healthcheck |
| `GET /templates` | — | Lista mallar (block-engine + recipe) |
| `GET /templates/{name}/schema` | — | JSON Schema för en mall |
| `GET /blocks` | — | Lista block-engine-blocktyper |
| `GET /blocks/{name}/schema` | — | JSON Schema för en blocktyp |
| `GET /page-templates` | — | Lista registrerade page-template-bundles |
| `GET /page-templates/{name}` | — | Metadata för en bundle |
| `POST /render` | **API_TOKEN** | JSON in, PDF out |
| `POST /page-templates` | **API_TOKEN** | Skapa eller ersätt en bundle (base64-JSON) |
| `DELETE /page-templates/{name}` | **API_TOKEN** | Ta bort en bundle |

Write-endpoints kräver `Authorization: Bearer $API_TOKEN`. Token sätts via env-var i `infra/.env` på servern (eller lokalt vid utveckling). Stopgap tills per-user auth landar — då migreras detta till Clerk-JWT-validering.

## Lokal utveckling

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Kör servern
uvicorn klartex_se.main:app --reload --port 8000

# Sätt API_TOKEN för write-endpoints
export API_TOKEN=$(openssl rand -hex 32)

# Starta servern med token i miljön
API_TOKEN=$API_TOKEN uvicorn klartex_se.main:app --reload --port 8000

# Smoke-test — discovery är publikt
curl http://localhost:8000/templates | jq '.[].name'

# /render kräver token
curl -X POST http://localhost:8000/render \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_TOKEN" \
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
