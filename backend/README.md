# backend/

FastAPI-app som importerar `klartex` (PyPI) som library och exponerar HTTP-API:t som klartex.se frontend använder.

Ersätter kärnans utfasade `klartex serve` (borttagen i klartex v0.11.0). HTTP-yta hör hemma här, där webbappens andra beslut (auth, persistens, asset-hantering) också bor.

## Endpoints

| Metod & path | Vad | Token |
|--------------|-----|-------|
| `GET /api/health` | Liveness — används av Docker healthcheck | Nej |
| `GET /api/templates` | Lista mallar (block-engine + recipe) | Nej |
| `GET /api/templates/{name}/schema` | JSON Schema för en mall | Nej |
| `GET /api/blocks` | Lista block-engine-blocktyper | Nej |
| `GET /api/blocks/{name}/schema` | JSON Schema för en blocktyp | Nej |
| `POST /api/render` | JSON in, PDF out. Max 2 samtidiga renders — fler ger 503 | Nej — utom `latex`-blocket |
| `GET /api/page-templates` | Lista registrerade sidmalls-bundles | Nej |
| `GET /api/page-templates/{name}` | Metadata för en bundle | Nej |
| `POST /api/page-templates` | Registrera eller ersätt en bundle (`.tex.jinja` + assets, base64) | Ja |
| `DELETE /api/page-templates/{name}` | Ta bort en bundle | Ja |

Multipart-varianten `/api/render-with-assets` (logo + `.tex.jinja`-upload) tillkommer i nästa iteration.

## Autentisering

Instansen bär en delad token i env-variabeln `API_TOKEN` (se `infra/.env.example`). Den presenteras som `Authorization: Bearer <token>`.

Två nivåer:

| Nivå | Vad som går att göra |
|------|----------------------|
| Anonym (ingen `Authorization`-header) | Discovery, `GET` på registret, och rendering av alla block **utom** `latex` |
| Token | Hela blockytan, inklusive `latex`, plus `POST`/`DELETE` på `/api/page-templates` |

En token låser upp *blockytan*, inte en högre kvot: Caddys tak på 10 anrop per minut och IP gäller båda nivåerna (kvot per nivå hör till #23).

Ett presenterat men felaktigt token ger `401` även på `/api/render` — anropet degraderas inte tyst till anonymt, så en trasig integration går att skilja från ett avsiktligt anonymt anrop. Saknas `API_TOKEN` på instansen svarar varje anrop som presenterar en token `503`; de anonyma vägarna fungerar ändå.

Tokenen är ett stopgap: en enda hemlighet som ger full åtkomst till alla bundles. Konton och self-serve-tokens är #19. Åtkomst ges på förfrågan tills dess — mejla kontakt@klartex.se.

## Felsvar från `/api/render`

Alla fel efter request-parsningen svarar med ett objekt under `detail`: alltid `type` och `message`, och `path` när felet går att peka ut i den inskickade `data`.

| `detail.type` | Status | När | `path` |
|---------------|--------|-----|--------|
| `validation_error` | 400 | Datat bryter mot mallens JSON Schema | Alltid |
| `input_error` | 400 | Blockvalidering, okänd mall, ogiltig `asset_dir` | När ett block kan pekas ut |
| `unknown_page_template` | 400 | `page_template` namnger ingen registrerad bundle | Nej |
| `token_required` | 401 | En `Authorization`-header presenterades utan `Bearer `-prefix | Nej |
| `invalid_token` | 401 | Ett token presenterades men stämmer inte | Nej |
| `token_required` | 403 | Anonymt anrop med ett `latex`-block; `block_type` namnger blocket | Alltid |
| `token_not_configured` | 503 | Ett token presenterades till en instans som saknar `API_TOKEN` | Nej |
| `overloaded` | 503 | Båda render-platserna upptagna (se nedan) | Nej |
| `render_error` | 500 | `xelatex` misslyckades | Nej |

`token_required` och `503` är var för sig tvetydiga: `detail.type` ensam räcker inte, utan en klient som förgrenar på feltyp måste läsa statuskoden också. `token_required` med `401` betyder att headern inte gick att tolka och bär varken `path` eller `block_type`; med `403` betyder den att anropet var giltigt som anonymt men innehåller ett `latex`-block, och då finns båda fälten. `503` betyder antingen `overloaded` eller `token_not_configured`.

`POST`/`DELETE /api/page-templates` svarar med samma `detail`-form: `401` (`token_required` när headern saknas, `invalid_token` när tokenen är fel) och `503` (`token_not_configured`). `403` förekommer bara på `/api/render`, där anropet var giltigt som anonymt men blocket kräver mer.

`path` är en lista som adresserar den felande noden i `data`, i samma form som jsonschemas `absolute_path`: `["body", 1]` för ett block, `["body", 0, "items", 0, "text"]` för ett fält inne i ett block, `[]` för roten av `data` (t.ex. när `body` saknas). En klient kan alltså markera rätt block utan att tolka `message`, vars formuleringar ägs av klartex-kärnan.

```json
{
  "detail": {
    "type": "input_error",
    "message": "Invalid 'text' block at body[1]: 'text' is a required property",
    "path": ["body", 1]
  }
}
```

Ett request som inte ens matchar `RenderRequest` — t.ex. `data` som inte är ett objekt, eller `template` som saknas — avvisas av FastAPI med `422` och pydantics egen form på `detail` (en lista av fel), inte formen ovan.

## Belastningstak på `/api/render`

En render startar `xelatex` två gånger med 60 s timeout per körning, så en handfull samtidiga anrop räcker för att mätta en liten VM. Endpointen tar därför en av två render-platser innan arbetet börjar. Är båda upptagna svaras `503` direkt — med `Retry-After: 5` och `detail.type = "overloaded"` — i stället för att köa.

Taket är per process och förutsätter **en** uvicorn-worker per container: fler workers eller repliker multiplicerar antalet samtidiga renders. Edge-lagret kompletterar med rate limit och body-gräns på `POST /api/render` (se `infra/Caddyfile`), och containern har CPU-/minnes-/pids-tak i `infra/docker-compose.yml`.

## Sidmall på `/api/render`

`page_template` på toppnivå väljer sidmall och tar två former:

| Form | Betydelse |
|------|-----------|
| Sträng | Namnet på en bundle registrerad via `/api/page-templates` |
| Objekt | Kärnans slot-form, som skickas vidare som `data.page_template` |

Slot-formen är två oberoende slots, `header` och `footer`. Varje slot är `null` (tom), ett variantnamn eller ett objekt med `variant` och variantens inställningar; en utelämnad slot får ytans default. Formen ägs av kärnan och står i mallens schema (`GET /api/templates/{name}/schema`).

En bundle bär en enda `page_template.tex.jinja` som beskriver hela sidan. Den skickas till kärnan som header-slotens källa och footern sätts till `null`, vilket ger samma sida som en helsidesmall. Bundlen äger därmed båda slotarna: både `header` och `footer` i `data.page_template` får ge vika. Dokumentinställningarna där — `font`, `header_font`, `diff_style`, `page_numbers` och `first_page_header` — gäller oförändrat.

## Assets i registrerade sidmallar

En sidmall registrerad via `/api/page-templates` sparas som en bundle: `page_template.tex.jinja` plus dess assets i samma katalog. Vid `/api/render` pekas klartex på bundle-katalogen, som blir både sökväg för `TEXINPUTS` och arbetskatalog för xelatex. Det ger två referensformer i mallen:

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
curl http://localhost:8000/api/templates | jq '.[].name'
curl -X POST http://localhost:8000/api/render \
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
