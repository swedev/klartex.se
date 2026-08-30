# backend/

FastAPI-app som bär hela den publika `/api`-ytan: discovery ur `klartex`-paketets scheman, tier-policy, sidmallsregistret och rendering.

Appen kompilerar inte själv. `POST /api/render` avgör vad anroparen får rendera, plockar ihop sidmallens källa och assets ur registret och skickar dokumentet vidare till render-tjänsten (`../render/`), som är den enda processen som kör `xelatex`. Delningen är poängen: anroparstyrd LaTeX kompileras i en container utan hemligheter, utan volymer och utan väg ut till internet, och den här imagen väger tiotals megabyte i stället för nio gigabyte.

Ersätter kärnans utfasade `klartex serve` (borttagen i klartex v0.11.0). HTTP-yta hör hemma här, där webbappens andra beslut (auth, persistens, asset-hantering) också bor.

## Endpoints

| Metod & path | Vad | Token |
|--------------|-----|-------|
| `GET /api/health` | Liveness — används av Docker healthcheck | Nej |
| `GET /api/templates` | Lista mallar (block-engine + recipe) | Nej |
| `GET /api/templates/{name}/schema` | JSON Schema för en mall | Nej |
| `GET /api/blocks` | Lista block-engine-blocktyper | Nej |
| `GET /api/blocks/{name}/schema` | JSON Schema för en blocktyp | Nej |
| `POST /api/render` | JSON in, PDF out. Proxas till render-tjänsten; max 2 samtidiga — fler ger 503 | Nej — utom `latex`-blocket |
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
| `unknown_page_template` | 400 | `page_template` är varken registrerad bundle eller inbyggd | Nej |
| `token_required` | 401 | En `Authorization`-header presenterades utan `Bearer `-prefix | Nej |
| `invalid_token` | 401 | Ett token presenterades men stämmer inte | Nej |
| `token_required` | 403 | Anonymt anrop med ett `latex`-block; `block_type` namnger blocket | Alltid |
| `token_not_configured` | 503 | Ett token presenterades till en instans som saknar `API_TOKEN` | Nej |
| `overloaded` | 503 | Båda render-platserna upptagna (se nedan) | Nej |
| `render_error` | 500 | `xelatex` misslyckades | Nej |
| `render_unavailable` | 502 | Render-tjänsten svarade inte, svarade för långsamt, eller svarade något oläsbart | Nej |

`validation_error`, `input_error`, `render_error` och `overloaded` formuleras av render-tjänsten och skickas vidare oförändrade — status, `detail` och `Retry-After` — så formuleringarna ägs där kärnans meddelanden tolkas. `render_unavailable` är det enda backend själv hittar på: den betyder att anropet aldrig blev besvarat och går att göra om.

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

Kompileringens tak sitter i render-tjänsten: två samtidiga renders, sedan `503` med `Retry-After: 5` och `detail.type = "overloaded"` i stället för kö (se `../render/README.md`). Backend håller ett lika stort tak på antalet anrop den har i luften mot den tjänsten, taget innan sidmallens bytes läses. Fler anrop än så skulle ändå bara kunna vänta på ett `503` därifrån, och taket är det som begränsar hur många bundle-payloads som byggs i minnet samtidigt.

Taken är per process och förutsätter **en** uvicorn-worker per container: fler workers eller repliker multiplicerar antalet samtidiga renders. Edge-lagret kompletterar med rate limit och body-gräns på `POST /api/render` (se `infra/Caddyfile`), och båda containrarna har CPU-/minnes-/pids-tak i `infra/docker-compose.yml`.

Svarar render-tjänsten inte alls blir svaret `502 render_unavailable`. Tidsbudgeten är uttalad och summerar under proxyns tak: kärnan kör `xelatex` två gånger med 60 s timeout per körning, klienten mot render-tjänsten ger upp efter som mest 165 s (5 s connect + 30 s write + 130 s read), och Caddy väntar 180 s på svarshuvudet — så ett strukturerat fel hinner alltid fram före proxyns egen timeout.

## Assets i registrerade sidmallar

En sidmall registrerad via `/api/page-templates` sparas som en bundle: `page_template.tex.jinja` plus dess assets i samma katalog. Vid `/api/render` läses bundlen härifrån och följer med anropet till render-tjänsten, som skriver den till en temporär katalog för just det anropet. Den katalogen blir både sökväg för `TEXINPUTS` och arbetskatalog för xelatex. Det ger två referensformer i mallen:

| Referens i mallen | Löses mot |
|-------------------|-----------|
| `\includegraphics{logo.pdf}` | bundlens katalog först, render-processens arbetskatalog som fallback |
| `\includegraphics{./logo.pdf}` | enbart bundlens katalog |

Heter en fil likadant i bundlen och i render-processens arbetskatalog vinner bundlens kopia. Assets laddas upp med filnamn utan sökvägsseparatorer, så referera dem med just filnamnet — sökvägar uppåt (`../`) pekar utanför bundlen och ingår inte i kontraktet.

## Lokal utveckling

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Kör servern. RENDER_URL pekar på en render-tjänst startad enligt
# ../render/README.md; utan den svarar /api/render 502 render_unavailable
# medan discovery och registret fungerar som vanligt.
RENDER_URL=http://localhost:8001 uvicorn klartex_se.main:app --reload --port 8000

# Smoke-test
curl http://localhost:8000/api/templates | jq '.[].name'
curl -X POST http://localhost:8000/api/render \
  -H "Content-Type: application/json" \
  -d '{"template":"_block","data":{"lang":"sv","body":[{"type":"heading","text":"Test"}]}}' \
  -o /tmp/test.pdf
```

Kontraktstestet (`tests/test_contract.py`) kör render-tjänsten i samma process som backend, så render-paketet måste finnas i testmiljön. Det kostar ingenting extra — det är render-tjänsten utan sin TeX-bas:

```bash
pip install -e ../render
```

Tester (`xelatex` behövs för de två kontraktstester som producerar en riktig PDF; de hoppas över när det saknas, och samma pytest-svit körs i CI före image-bygget):

```bash
pytest -q -rs
pytest tests/test_discovery.py   # bara discovery (snabbt)
```

## Docker

Imagen byggs på `python:3.12-slim` och installerar projektet ur `pyproject.toml` i ett venv. Ingen TeX Live: den bor i render-tjänstens image, som har sin egen versionsserie. Bygget tar sekunder och imagen väger tiotals megabyte.

```bash
docker build -t klartex-se-backend:dev .
docker run --rm -p 8000:8000 -e RENDER_URL=http://host.docker.internal:8001 klartex-se-backend:dev
```

Healthchecken är en `python -c`-rad i stället för `curl`, som slim-imagen saknar. `infra/docker-compose.yml` upprepar samma kommando: en `healthcheck:` i compose-filen ersätter imagens.

## Deploy

App-imagen byggs av `.github/workflows/deploy.yml`, och bara när en `v*`-tagg pushas: tester, multi-arch-bygge (amd64 + arm64) till `ghcr.io/swedev/klartex-se-backend`, smoke-test av amd64-imagen innan något publiceras, och därefter utrullning. Smoke-testet startar den nybyggda imagen tillsammans med den render-image `infra/.env.example` pinnar och kör hela kedjan, så en release provas i den parning den deployas i. En push till `main` bygger ingenting — `ci.yml` kör testerna och inget mer.

`klartex`-pinnen måste vara identisk i `pyproject.toml` här och i `../render/pyproject.toml` — discovery-scheman kommer från den ena kärnan och renderingen från den andra. CI jämför pinnarna, och deployen jämför vad de två health-endpointsen rapporterar. En kärnbump rullas ut i ordningen `render` först, `backend` sedan.

För produktion: bumpa `version` i `pyproject.toml` och `__version__` i `src/klartex_se/__init__.py`, merga, och pusha en matchande `v*`-tagg.
