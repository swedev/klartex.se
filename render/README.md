# render/

Intern render-tjänst: en tillståndslös HTTP-inpackning av `klartex.render()`. Det är den enda processen i stacken som kör `xelatex`, och den enda imagen som bär TeX Live.

Tjänsten känner inte till konton, tokens, sidmallsregistret eller något annat i produkten. Den tar ett dokument och det den behöver för att kompilera det, och lämnar tillbaka en PDF. Hela poängen är att den processen inte delar miljö med instansens hemligheter: `render` har ingen `environment`, inga volymer, ingen publicerad port och ligger på ett compose-nätverk med `internal: true`.

**`render` ska aldrig exponeras publikt.** Den är nåbar enbart från `backend` på compose-nätverket, och den gör ingen autentisering — policyn för vem som får rendera vad ligger i `backend`.

## Kontrakt

Två endpoints, utan `/api`-prefix. Inget OpenAPI-schema publiceras.

| Metod & path | Vad |
|--------------|-----|
| `GET /health` | Liveness — används av Docker healthcheck och av deployen |
| `POST /render` | JSON in, `application/pdf` ut |

`GET /health` svarar med tjänstens egen version och den installerade kärnversionen:

```json
{"status": "ok", "version": "0.1.0", "klartex": "0.15.0"}
```

Deployen skriver ut båda tjänsternas health-svar sida vid sida: discovery-scheman kommer från kärnan i `backend` och renderingen från kärnan här, och de måste vara samma version.

### `POST /render`

Kroppen speglar `klartex.render()`s signatur, med `asset_dir` ersatt av filerna själva:

```json
{
  "template": "_block",
  "data": {"lang": "sv", "body": [{"type": "heading", "text": "Hej"}]},
  "page_template_source": "\\fancyhead[R]{\\includegraphics{logo.pdf}}",
  "assets": {"logo.pdf": "<base64>"}
}
```

`page_template_source` och `assets` är valfria. Skickas någon av dem skrivs `assets` till en temporär katalog som blir xelatex arbetskatalog och `TEXINPUTS`-sökväg för anropet, och tas bort när svaret är skrivet. Skickas ingen av dem körs renderingen utan asset-katalog, precis som kärnan gör på egen hand.

Filnamnen i `assets` måste matcha `[A-Za-z0-9][A-Za-z0-9._-]{0,127}` — samma regel som sidmallsregistret sätter på lagrade filnamn. Den kontrolleras här igen: ingen anropare, inte ens en felaktig `backend`, ska kunna skriva utanför den temporära katalogen. Gränserna följer också registret: högst 10 assets, 5 MB per asset, 1 MB `page_template_source`. Ett request vars `Content-Length` överstiger 80 MB avvisas med `413` innan kroppen läses.

### Felsvar

Alla fel efter request-parsningen svarar med ett objekt under `detail`: alltid `type` och `message`, och `path` när felet går att peka ut i den inskickade `data`.

| `detail.type` | Status | När | `path` |
|---------------|--------|-----|--------|
| `validation_error` | 400 | Datat bryter mot mallens JSON Schema | Alltid |
| `input_error` | 400 | Blockvalidering, okänd mall, ogiltigt assetnamn, ogiltig base64, för stor asset | När ett block kan pekas ut |
| `payload_too_large` | 413 | `Content-Length` över 80 MB | Nej |
| `render_error` | 500 | `xelatex` misslyckades | Nej |
| `overloaded` | 503 | Båda render-platserna upptagna; `Retry-After: 5` | Nej |

Formerna är desamma som `/api/render` svarar med utåt, och kontraktet är att `backend` skickar status, `detail` och `Retry-After` vidare oförändrade. Felmeddelandenas formuleringar ägs alltså här — nära den kärna vars meddelanden de tolkar.

## Belastningstak

En render startar `xelatex` två gånger med 60 s timeout per körning. Endpointen tar därför en av två render-platser innan arbetet börjar; är båda upptagna svaras `503` direkt i stället för att köa.

Taket är per process och förutsätter **en** uvicorn-worker per container: fler workers eller repliker multiplicerar antalet samtidiga renders. `backend` sätter ett in-flight-tak av samma storlek framför sin proxning, så ett tredje samtidigt anrop stoppas redan där.

## Lokal utveckling

```bash
cd render
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

uvicorn klartex_render.main:app --reload --port 8001
```

```bash
curl http://localhost:8001/health
curl -X POST http://localhost:8001/render \
  -H "Content-Type: application/json" \
  -d '{"template":"_block","data":{"lang":"sv","body":[{"type":"heading","text":"Test"}]}}' \
  -o /tmp/test.pdf
```

Tester (`xelatex` behövs för render-testerna; de hoppas över när det saknas, precis som i CI):

```bash
pytest -q -rs
```

## Docker

Imagen är tvådelad. De tunga, sällan ändrade lagren — TeX Live-basen, apt-paketen, Microsofts kärnfonter och `texlive-bin`-symlänken — bor i basimagen `ghcr.io/swedev/klartex-base`, som byggs och publiceras från `swedev/klartex` (`docker/Dockerfile.base` via dess `base-image.yml`). `Dockerfile` bygger tjänsten ovanpå den: ett venv där projektet installeras ur `pyproject.toml`. Ett bygge tar därför ett par minuter i stället för att bygga om ~7 GB.

```bash
docker build -t klartex-se-render:dev .
docker run --rm -p 8001:8000 klartex-se-render:dev
```

Basimagen hämtas från GHCR vid bygget. Paketet är publikt, så ingen inloggning behövs.

### Bumpa basimagen

1. Bumpa basen i `swedev/klartex` (dess `docker/Dockerfile.base`) och invänta att `base-image.yml` där bygger multi-arch och publicerar en ny tagg, `YYYYMMDD-<run_number>`.
2. Kopiera image-referensen `ghcr.io/swedev/klartex-base:<tagg>@<digest>` ur publiceringskörningens step-summary. Digesten går också att läsa av med `docker buildx imagetools inspect ghcr.io/swedev/klartex-base:<tagg>`.
3. Uppdatera `FROM`-raden i `Dockerfile` till den referensen i en egen PR.

Pinnen bär både tagg och digest: taggen för läsbarhet, digesten för att bygget ska vara reproducerbart. Ingen `latest`-tagg publiceras. Publicerade bastaggar får inte raderas så länge någon `Dockerfile` i historiken refererar dem — då går de byggena inte att reproducera.

## Deploy

Imagen byggs av `.github/workflows/deploy.yml`, och bara när en `render-v*`-tagg pushas: tester, multi-arch-bygge (amd64 + arm64) till `ghcr.io/swedev/klartex-se-render`, smoke-test av amd64-imagen innan något publiceras, och därefter utrullning.

Serien är skild från `backend`s `v*`-serie med flit: en produktrelease ska inte flytta TeX-basen genom CI igen. `klartex`-pinnen måste däremot vara identisk i `render/pyproject.toml` och `backend/pyproject.toml`, och CI kontrollerar det.

En kärnbump rullas alltid ut i ordningen `render` först, `backend` sedan. Renderaren validerar varje anrop mot sin egen kärna, så fönstret däremellan är ofarligt: ett dokument byggt mot en äldre discovery renderas ändå. Den farliga riktningen är den omvända, där discovery erbjuder block renderaren inte känner.

För produktion: bumpa `version` i `pyproject.toml` och `__version__` i `src/klartex_render/__init__.py`, bumpa `RENDER_VERSION` i `infra/.env.example`, merga, och pusha en matchande `render-v*`-tagg.
