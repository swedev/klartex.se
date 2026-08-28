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
| `POST /render` | JSON in, PDF out. Max 2 samtidiga renders — fler ger 503 |
| `GET /page-templates` | Lista registrerade sidmalls-bundles |
| `GET /page-templates/{name}` | Metadata för en bundle |
| `POST /page-templates` | Registrera eller ersätt en bundle (`.tex.jinja` + assets, base64) — kräver `ADMIN_TOKEN` |
| `DELETE /page-templates/{name}` | Ta bort en bundle — kräver `ADMIN_TOKEN` |

Multipart-varianten `/render-with-assets` (logo + `.tex.jinja`-upload) tillkommer i nästa iteration.

## Belastningstak på `/render`

En render startar `xelatex` två gånger med 60 s timeout per körning, så en handfull samtidiga anrop räcker för att mätta en liten VM. Endpointen tar därför en av två render-platser innan arbetet börjar. Är båda upptagna svaras `503` direkt — med `Retry-After: 5` och `detail.type = "overloaded"` — i stället för att köa.

Taket är per process och förutsätter **en** uvicorn-worker per container: fler workers eller repliker multiplicerar antalet samtidiga renders. Edge-lagret kompletterar med rate limit och body-gräns på `POST /render` (se `infra/Caddyfile`), och containern har CPU-/minnes-/pids-tak i `infra/docker-compose.yml`.

## Assets i registrerade sidmallar

En sidmall registrerad via `/page-templates` sparas som en bundle: `page_template.tex.jinja` plus dess assets i samma katalog. Vid `/render` pekas klartex på bundle-katalogen, som blir både sökväg för `TEXINPUTS` och arbetskatalog för xelatex. Det ger två referensformer i mallen:

| Referens i mallen | Löses mot |
|-------------------|-----------|
| `\includegraphics{logo.pdf}` | bundle-katalogen först, serverns arbetskatalog som fallback |
| `\includegraphics{./logo.pdf}` | enbart bundle-katalogen |

Heter en fil likadant i bundlen och i serverns arbetskatalog vinner bundlens kopia. Assets laddas upp med filnamn utan sökvägsseparatorer, så referera dem med just filnamnet — sökvägar uppåt (`../`) pekar utanför bundlen och ingår inte i kontraktet.

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

Tester (`xelatex` behövs för render-tester; de hoppas över när det saknas, och samma pytest-svit körs i CI före image-bygget):

```bash
pytest
pytest -k "not render"   # bara discovery-tester (snabbt, ingen xelatex)
```

## Docker

Imagen är tvådelad. De tunga, sällan ändrade lagren — TeX Live-basen, apt-paketen, Microsofts kärnfonter och `texlive-bin`-symlänken — bor i basimagen `ghcr.io/swedev/klartex-base`, som byggs och publiceras från `swedev/klartex` (`docker/Dockerfile.base` via dess `base-image.yml`). `Dockerfile` bygger app-imagen ovanpå den: venv med de pinnade beroendena plus `src/`. Ett app-bygge tar därför ett par minuter i stället för att bygga om ~7 GB.

```bash
docker build -t klartex-se-backend:dev .
docker run --rm -p 8000:8000 klartex-se-backend:dev
```

Basimagen hämtas från GHCR vid bygget. Paketet är publikt, så ingen inloggning behövs.

### Bumpa basimagen

1. Bumpa basen i `swedev/klartex` (dess `docker/Dockerfile.base`) och invänta att `base-image.yml` där bygger multi-arch och publicerar en ny tagg, `YYYYMMDD-<run_number>`.
2. Kopiera image-referensen `ghcr.io/swedev/klartex-base:<tagg>@<digest>` ur publiceringskörningens step-summary. Digesten går också att läsa av med `docker buildx imagetools inspect ghcr.io/swedev/klartex-base:<tagg>`.
3. Uppdatera `FROM`-raden i `Dockerfile` till den referensen i en egen PR.

Pinnen bär både tagg och digest: taggen för läsbarhet, digesten för att bygget ska vara reproducerbart. Ingen `latest`-tagg publiceras. Publicerade bastaggar får inte raderas så länge någon `Dockerfile` i historiken refererar dem — då går de byggena inte att reproducera.

## Deploy

App-imagen byggs av `.github/workflows/deploy.yml`, och bara när en `v*`-tagg pushas: tester, multi-arch-bygge (amd64 + arm64) till `ghcr.io/swedev/klartex-se-backend`, smoke-test av amd64-imagen innan något publiceras, och därefter utrullning. En push till `main` bygger ingenting — `ci.yml` kör testerna och inget mer.

För produktion: bumpa `version` i `pyproject.toml` och `__version__` i `src/klartex_se/__init__.py`, merga, och pusha en matchande `v*`-tagg.
