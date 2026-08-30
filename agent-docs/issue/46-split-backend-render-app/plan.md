# Plan: Issue #46 — Split the backend into a render service and an app service

## Mål

Dela dagens enda backend-container i två compose-tjänster:

- **`render`** — processen som kör xelatex. Den är **kärnans artefakt**: `swedev/klartex` bygger och publicerar `ghcr.io/swedev/klartex-render:<kärnversion>` vid varje release, och klartex.se konsumerar imagen utan att någonsin bygga den. Kärnrepots halva är swedev/klartex#81 (`klartex serve` + release-jobbet som pushar imagen).
- **`backend`** (issuets "app") — dagens FastAPI-app minus kompileringen: discovery, auth/tier-policy, page-template-registret och all publik `/api`-trafik, på `python:3.12-slim`. Kompilering proxas till `render`. Det är hit Postgres, konton och parla (#19), dokumentpersistens och den anonyma nivån (#23) läggs.

Att render-motorn versioneras som kärnan följer av att de två alltid rör sig ihop: det finns ingen kärnrelease som lämnar renderaren orörd, och ingen ändring i renderaren som inte är en kärnrelease. klartex.se har därmed **en** kärn-pin och en egen appversion — inga två versionsserier att hålla i synk.

Resultatet ska vara osynligt för API-klienter utom två avsiktliga ändringar: `502 render_unavailable` tillkommer, och sidmalls-aliasen `formal`/`clean`/`none` försvinner ur det publika kontraktet (användarbeslut, se Designbeslut 2). Skillnaden i drift är att processen som kör anroparstyrd LaTeX inte längre delar miljö med någon hemlighet, att ett produktrelease flyttar megabyte i stället för gigabyte, och att #19 kan byggas i rätt behållare från början.

## Triagering

> Beslutsunderlag för detta issue.

| Fält | Värde |
|------|-------|
| **Blockeras av** | swedev/klartex#81 för PR 2a och 2b (kärnreleasen som bär alias-borttagningen, `klartex serve` och render-imagen). PR 0 blockeras av inget. |
| **Blockerar** | #19 (konton/Postgres ska födas i `backend`, inte i TeX-containern), #47 (miljöexponeringen stängs av detta), #23 (payload-policyn i app-lagret) |
| **Relaterade issues** | #47, #19, #23, #39, #20, #18, #64, #14, swedev/klartex#81, swedev/klartex#51 |
| **Omfattning** | `backend/` (src, tests, Dockerfile, README), `infra/`, `.github/workflows/`, `llms.txt`, `index.html`, docs |
| **Risk** | Medel |
| **Komplexitet** | Medel |
| **Säker för junior** | Nej — publikt API-kontrakt, produktionsutrullning, deploy-workflow och compose-topologi |
| **Konfliktrisk** | Låg — inga öppna planer rör samma filer aktivt; den omergade #14-grenen ändrar enbart `app/` |

### Triagemässiga noteringar

- **Kärnberoendet är hårt för 2a och 2b.** Båda kräver att kärnreleasen som bär alias-borttagningen och `klartex serve` ligger på PyPI; 2b kräver dessutom att `ghcr.io/swedev/klartex-render:<den versionen>` finns på GHCR. Det arbetet spåras i swedev/klartex#81 och görs inte här.
- **Ordningen mot #19 är poängen.** Issuet argumenterar att Postgres/parla ska byggas in i `backend` *efter* splitten. #19 bör därför inte påbörjas förrän PR 2b är mergad.
- **#47 stängs till hälften av #15 (0.5.0).** Det som återstår i #47 är miljöexponeringen i sig — exakt det `render` utan hemligheter löser. PR 2b bär `Closes #46, closes #47`; verifiera vid PR-tillfället att inget nytt tillkommit i #47.
- **#18 (assets per anrop)** får sitt interna kontrakt gratis: kärnans `/render` tar bundle-innehållet inline. Den publika varianten på `/api/render` är fortfarande #18:s sak.
- **#39 (releasebygget flyttar 9 GB)** löses helt för klartex.se: repot bygger ingen TeX-image alls efter splitten. Kostnaden ligger i kärnans release-flöde, några gånger per år.
- **#64 (per-slot-bundlar)** är följdarbetet efter 2a. Registret bär en monolitisk `page_template.tex.jinja`, och shimmen i 2a översätter den till kärnans slot-API. Att bundle-formatet självt får `header`/`footer` hör hemma i #64.
- **GHCR-paketets synlighet** är kärnrepots fälla, inte klartex.se:s: `klartex-render` skapas av kärnans första publicerande release och måste sättas publikt för hand (samma sak som klartex.se#48 dokumenterade för basen). Är paketet privat stannar `docker compose pull` — före omstarten, med stacken orörd.
- **Minnesbudgeten på cax11 (4 GB)** ska mätas efter `v0.6.0` innan taken låses. Splitten i sig ökar inte totalen, men Postgres i #19 får inte plats i marginalen utan att antingen `render`s tak sänks efter mätning eller värden storleksändras (cax21, 8 GB). Det avgörs i #19. Se Designbeslut 9.
- **Frontend-bygget** (issuets "and the frontend build" under `app`) ligger utanför: källan finns bara på #14-grenen och Caddy servar `~/app` statiskt idag.

## Angreppssätt

### Vad som flyttar vart

`backend/src/klartex_se/render.py` innehåller två sorters kod som ska isär:

| Kod | Är | Hamnar i |
|-----|----|----------|
| `find_latex_block`, `_child_block_lists`, tier-kontrollen (403) | Policy — vad anroparen får göra | `backend` |
| Bundle-uppslag mot registret (`get_bundle_path`, `load_bundle_payload`) | Policy/lagring | `backend` |
| `_block_error_path`, `_BLOCK_ERROR_RE`, mappning `ValidationError`/`ValueError`/`RuntimeError` → 400/500 | Kärnnära — beror på kärnans meddelandeformer | Kärnan (`klartex.server`) |
| Semaforen kring xelatex (max 2 samtidiga, 503 `overloaded`) | Skydd av processen som kör xelatex | Kärnan (`klartex.server`) |
| `klartex.render(...)`-anropet | Kompilering | Kärnan (`klartex.server`) |

Discovery (`/api/templates`, `/api/blocks`, scheman) stannar i `backend`: rena Python-anrop mot `klartex`-paketet utan TeX, och `find_latex_block`s test pinnar sig mot kärnans `_child_block_lists`. `backend` behåller därför `klartex` som pip-beroende — utan TeX-basen väger imagen några tiotal MB.

### Det interna kontraktet `backend → render`

Kontraktet ägs av kärnan (swedev/klartex#81) och är internt: ingen publik yta, ingen auth, ingen docs-sida.

- `GET /health` → `{"status": "ok", "version": "<kärnversion>"}`
- `POST /render` body `{"template": str, "data": object, "header_source": str?, "footer_source": str?, "assets": {name: base64}?}` → `200 application/pdf`
- Fel: `400 {"detail": {"type": "input_error"|"validation_error", "message", "path"?}}`, `413 payload_too_large`, `500 render_error`, `503 overloaded` med `Retry-After`

`render` skriver `assets` till en temporär katalog per anrop, kompilerar och städar. Inga volymer, inget tillstånd, ingen kännedom om registret. `backend` skickar bundle-innehållet inline och passar felen vidare oförändrade — det enda nya i det publika kontraktet är `502 render_unavailable` när `backend` inte når `render` eller anropet tar för lång tid.

### Sekvens i `backend`s `/api/render` efter splitten

1. Tier-kontroll: anonymt anrop med `latex`-block → 403 (oförändrat).
2. `page_template`: objekt → skickas rakt igenom till kärnans slot-form; sträng → registrerat bundle-namn; okänt namn → 400 `unknown_page_template`. Bundlens *innehåll* läses först i steg 4, innanför semaforen.
3. Ta en av `MAX_INFLIGHT_RENDERS = 2` platser (icke-blockerande semafor, annars 503 `overloaded` + `Retry-After: 5`, samma form som `render`s). Samma tal som kärnans semafor: fler in-flight-anrop kan ändå bara vänta på ett 503, och två är den övre gränsen för hur många bundle-payloads (~68 MB base64 i värsta fall, plus JSON-kopior) som byggs samtidigt.
4. Bundle-namn → läs `page_template.tex.jinja` och alla assets ur registret, base64:a dem, och skicka källan som `header_source` med `data.page_template.footer = null` (Designbeslut 11).
5. `POST {RENDER_URL}/render` med `httpx.Client(timeout=httpx.Timeout(connect=5, read=130, write=30, pool=5))`. Tidsbudgeten summerar även i värsta fall under proxyns tak: kärnans xelatex-tak är 2 × 60 s; `httpx` kan i värsta fall ta 5 + 30 + 130 = 165 s; Caddys `response_header_timeout` sätts till **180 s** så att `backend` alltid hinner svara med ett strukturerat fel innan Caddy ger upp.
6. Svarshantering, i denna ordning:
   - 200 → PDF med `Content-Disposition` (oförändrat).
   - Status i {400, 500, 503} och en body vars `detail` är ett objekt med `type` och `message` → samma status, det inre `detail`-objektet oförändrat (aldrig `{"detail": {"detail": …}}`), och `Retry-After` vidarebefordrad om den finns. Inga andra headers passerar.
   - Allt annat (422 från pydantic i kärnan, HTML, ogiltig JSON, oväntad status) → 502 `render_unavailable` med ett generiskt meddelande; svaret loggas server-side.
   - `httpx.TransportError` (inklusive timeout) → 502 `render_unavailable`. Meddelandet nämner varken undantagstexten eller värdnamnet `render`.

### En image från kärnan, en pin i klartex.se

| | `backend` | `render` |
|---|---|---|
| Byggs av | klartex.se | `swedev/klartex` vid varje release |
| Katalog | `backend/` | — (ingen källa i detta repo) |
| Image | `ghcr.io/swedev/klartex-se-backend:<appversion>` | `ghcr.io/swedev/klartex-render:<kärnversion>` |
| Tagg som släpper | `v0.6.0` | kärnans egen release |
| `.env` | `BACKEND_VERSION` | `KLARTEX_VERSION` |
| Bas | `python:3.12-slim` | `ghcr.io/swedev/klartex-base` (kärnan pinnar) |

`KLARTEX_VERSION` är inte en egen versionsserie utan en avledning: **källan är `klartex==X.Y.Z` i `backend/pyproject.toml`**. Tre saker håller det sant:

- `infra/.env.example` bär samma värde, och CI felar om de två skiljer sig.
- Deployen skriver **både** `BACKEND_VERSION` och `KLARTEX_VERSION` till serverns `.env` vid varje backend-deploy. En kärnbump är därmed en PR plus en tagg, utan ssh; en rollback via `workflow_dispatch` från en äldre tagg återställer det matchande paret.
- Health-svaren jämförs efter omstarten: `backend`s `klartex`-fält mot `render`s `version`-fält (kärnan rapporterar sin egen version som `version`).

Rollback till `v0.5.x` fungerar oförändrat: den taggens compose-fil saknar `render`, och `--remove-orphans` i systemd-uniten städar containern. En kvarvarande `KLARTEX_VERSION=`-rad i `.env` är harmlös.

## Steg

### Fas 0: Återställ deploybarheten (PR 0)

`main` bär en compose-fil som kräver `${RENDER_VERSION:?}` och en deploy som kontrollerar att en `render`-tjänst kör. Ingen av delarna finns på servern, så varje `v0.5.x`-tagg från `main` stannar vid `docker compose pull` — restore-trappen återställer, stacken förblir orörd och deployen blir röd. `pins`-jobbet i CI felar dessutom så snart backendens kärn-pin bumpas. PR 0 tar bort båda hindren och lämnar trädet exakt i `v0.5.0`:s form.

1. Ta bort `render/` i sin helhet — kärnan äger render-tjänsten, klartex.se har ingen källa för den.
2. `infra/docker-compose.yml`: ta bort tjänsten `render` och det interna nätverket `render`; `backend` tillbaka på ett enda nätverk med taken 2560m / 1.5 CPU.
3. `.github/workflows/deploy.yml`: ta bort `render-v*`-triggern och `resolve`-jobbet; tillbaka till ett `v*`-flöde som bygger, smoke-testar, publicerar och rullar ut `backend`.
4. `.github/workflows/ci.yml`: ta bort `render`-posten ur matrisen och hela `pins`-jobbet — det finns bara en pin att vakta, och den vaktas mot `.env.example` från och med PR 2b.
5. `infra/.env.example`: ta bort `RENDER_VERSION`.
6. `infra/README.md`: rensa alla render-referenser (tabellrader, "Uppgradera", GHCR-avsnittet, säkerhet, felsökning).

**Resultatet:** stacken är två containrar (`backend`, `caddy`), `docker compose config` kräver bara `BACKEND_VERSION` med `API_TOKEN` valfri, och en `v0.5.1` kan släppas samma dag. PR 0 stänger inget issue: `Refs #46`. Tier `light`.

### Fas 1: Kom ikapp kärnan (PR 2a)

Körs på den monolitiska imagen, innan render-imagen konsumeras. Kräver att kärnreleasen från swedev/klartex#81 finns på PyPI.

1. `backend/pyproject.toml` + `backend/src/klartex_se/__init__.py`: bumpa `klartex==` till den releasen.
2. `backend/src/klartex_se/render.py`: `klartex.render()` tar inte längre `page_template_source`. Anropet skickar `header_source`; utan bundle skickas ingen källa alls.
3. **Aliasen försvinner ur det publika API:t** (Designbeslut 2). `BUILTIN_PAGE_TEMPLATES` raderas. `page_template` blir `str | object`: sträng = registrerat bundle-namn, objekt = kärnans slot-form rakt igenom. Ingen mappning, ingen kvarlevande konvention.
4. **Bundle-shimmen** (Designbeslut 11): registret bär en monolitisk `page_template.tex.jinja`. Den skickas som `header_source` och `data.page_template.footer` sätts till `null`, vilket ger samma emission som en delad källa utan footer. Bundlen vinner över ett anropar-skickat `footer`; det dokumenteras i `backend/README.md`.
5. Publika exempel rensas från alias-namnen: `RenderRequest`-exemplen i `render.py`, `backend/README.md`, `llms.txt` och `index.html`.
6. Tester: `page_template` som objekt når kärnan oförändrat, sträng slår upp bundlen, okänt namn → 400, shimmen sätter `header_source` + `footer: null`, inget test refererar `formal`/`clean`/`none`.
7. Release-noten nämner att kärnans footer-variant `standard` heter `pagenumber` (inget i klartex.se refererar den) och att inline-markup tolkas i fler block — det senare noteras för #14, ingen kodändring.

Tier `full` — det publika kontraktet ändras.

### Fas 2: Proxy, slim image och konsumtion av render-imagen (PR 2b)

Kräver att `ghcr.io/swedev/klartex-render:<pin>` finns på GHCR och är publik.

1. `backend/src/klartex_se/render_client.py` (ny)
   - `RENDER_URL = os.environ.get("RENDER_URL", "http://render:8000")`
   - `class RenderUpstreamError(Exception)` med `status_code`, `detail`, `headers`
   - `render_pdf(template, data, header_source, footer_source, assets) -> bytes` med en modulglobal `httpx.Client` och tidsbudgeten ovan; svarsalgoritmen exakt som i Angreppssätt steg 6
   - Klienten byggs via en modulfunktion `_client()` som tester kan monkeypatcha
2. `backend/src/klartex_se/render.py`: kompileringen, felmappningen och `_block_error_path` bort; semaforen blir `MAX_INFLIGHT_RENDERS = 2` och tas *före* bundle-laddningen så att den täcker både payload-bygget och proxy-anropet; `RenderUpstreamError` → `HTTPException` med status, detail och headers; `responses`-dokumentationen får 502.
3. `backend/src/klartex_se/page_templates.py`: `load_bundle_payload(name) -> tuple[str, dict[str, str]]` — template-källa plus assets som base64. En asset som saknas på disk eller en källa som inte är giltig UTF-8 ger `PageTemplateError` → 400 `input_error`; bundlen är då trasig, inte anropet.
4. `backend/pyproject.toml` + `__init__.py`: version `0.6.0`; `httpx>=0.27` som huvudberoende; `klartex[serve]` i `dev`-extran för kontraktstestet. `klartex` förblir runtime-beroende för discovery.
5. `backend/Dockerfile`: `FROM python:3.12-slim`; venv med `klartex`, `fastapi`, `uvicorn`, `httpx`, `python-multipart`; `HEALTHCHECK` via `python -c "import urllib.request; …"` (slim har ingen curl).
6. Tester
   - `backend/tests/test_render.py`: `fake_render`-fixturen monkeypatchar `render_pdf`; behåll tier-, 403-, `find_latex_block`- och carrier-pinning-testerna; nya för payload-bygge, upstream-passthrough (400/503 med `Retry-After`), in-flight-semaforen och 502 vid transportfel
   - `backend/tests/test_render_client.py` (ny): `render_pdf` mot `httpx.MockTransport` — 200 → bytes, 400/503 → `RenderUpstreamError`, 422/HTML/ogiltig JSON/okänd status → 502, `ConnectError`/`ReadTimeout` → 502, meddelandet innehåller inte värdnamnet
   - `backend/tests/test_contract.py` (ny): kontraktstest i process — `_client()` monkeypatchas till `starlette.testclient.TestClient(klartex.server.app)`, så att `backend`s payload verkligen parsas av kärnans pydantic-modell och kärnans felform verkligen passerar `backend`s validering
   - `backend/tests/test_page_templates.py`: enhetstester för `load_bundle_payload` inklusive trasiga bundles
7. `infra/docker-compose.yml`
   - `render: image: ghcr.io/swedev/klartex-render:${KLARTEX_VERSION:?…}`, inga `ports`, inga volymer, ingen `environment` med hemligheter, `restart: unless-stopped`
   - Nätverket `render` med `internal: true`; `backend` på både `default` och `render`, med `depends_on: render: condition: service_healthy`
   - Compose-proben använder samma URL som imagens `HEALTHCHECK`
   - **Härdning** (Designbeslut 10): `security_opt: [no-new-privileges:true]`, `cap_drop: [ALL]`, `read_only: true`, `tmpfs: [/tmp:size=512m]` och en skrivbar `HOME` på tmpfs (fontconfig kräver det, annars loggas "No writable cache directories" per körning)
   - Slutgiltiga tak: `render` 1792m / 1.5 CPU / `pids_limit 256`, `backend` 768m / 0.5 CPU / `pids_limit 128`
   - Compose-healthchecken för `backend` byts till samma `python -c "import urllib.request; …"` som imagen — compose-nivån åsidosätter imagens, och slim-imagen har ingen curl
8. `infra/.env.example`: `KLARTEX_VERSION` med samma värde som backendens `klartex==`-pin, och `BACKEND_VERSION=0.6.0`.
9. `.github/workflows/ci.yml`: ett steg som felar om `KLARTEX_VERSION` i `.env.example` skiljer sig från `klartex==`-pinnen i `backend/pyproject.toml`.
10. `.github/workflows/deploy.yml`
    - Smoke-testet startar en tvåcontainer-stack: `ghcr.io/swedev/klartex-render:<pin>` pullad från GHCR plus den nybyggda `backend`-imagen på ett tillfälligt nätverk. Kör `GET /api/health`, `GET /api/templates` innehåller `_block`, `POST /api/render` med `latex`-block → 403, och `POST /api/render` med minimal `_block`-body → `%PDF` (hela kedjan)
    - Deploy-steget skriver både `BACKEND_VERSION` och `KLARTEX_VERSION` till serverns `.env`; `docker compose ps`-kontrollen omfattar `backend render caddy`; efter omstarten jämförs `backend`s `klartex`-fält mot `render`s `version`-fält, och ett riktigt render-anrop körs medan restore-trappen fortfarande är armerad
11. `infra/Caddyfile`: `response_header_timeout` 180 s, med tidsbudgeten i kommentaren.
12. Dokumentation i nu-state: `backend/README.md` (rollen som policy-lager, 502 i felsvarstabellen, belastningstaket ligger i `render`, slim-imagen, lokal utveckling mot `RENDER_URL=http://localhost:8001` med `klartex serve`), `infra/README.md` (två tjänster, en pin, härdningen, säkerhet, felsökning), `PLAN.md` (API-image och hosting), `CLAUDE.md` (kärnprincip 1: kompilering sker i kärnans render-image, `backend/` är policy).

PR 2b bär `Closes #46, closes #47`. Tier `full`.

### Fas 3: Utrullning och mätning

1. Merga PR 2b → tagga `v0.6.0`. Stannar `docker compose pull` på paketets synlighet: sätt `klartex-render` publikt i kärnorganisationens paketvy och kör om via `workflow_dispatch`.
2. Verifiera: `/api/health` rapporterar 0.6.0 och samma kärnversion som `render`; render med registrerad bundle ger PDF med logotyp; anonymt `latex`-block ger 403.
3. Kontrollera på servern att `docker compose exec render env` saknar `API_TOKEN` och att `curl -m 5 https://example.com` från `render` misslyckas.
4. Mät med `docker stats --no-stream` under en riktig rendering; justera taken i en följdcommit. Uppdatera #19 med att `backend` är platsen för Postgres/parla och att minnesmarginalen är en förutsättning där.

## Filöversikt

| Fil | Fas | Åtgärd | Syfte |
|-----|-----|--------|-------|
| `render/` | 0 | Ta bort | Kärnan äger render-tjänsten |
| `infra/docker-compose.yml` | 0 | Ändra | Tillbaka till `backend` + `caddy`, tak 2560m / 1.5 CPU |
| `infra/.env.example` | 0 | Ändra | `RENDER_VERSION` bort |
| `infra/README.md` | 0 | Ändra | Render-referenser bort |
| `.github/workflows/deploy.yml` | 0 | Ändra | Ett `v*`-flöde; `render-v*` och `resolve` bort |
| `.github/workflows/ci.yml` | 0 | Ändra | Matrisen och `pins`-jobbet bort |
| `backend/pyproject.toml`, `backend/src/klartex_se/__init__.py` | 1, 2 | Ändra | Kärn-pin; 0.6.0; `httpx`; `klartex[serve]` i dev |
| `backend/src/klartex_se/render.py` | 1, 2 | Ändra | `header_source`; aliasen bort; policy + proxy |
| `backend/src/klartex_se/page_templates.py` | 2 | Ändra | `load_bundle_payload` |
| `backend/src/klartex_se/main.py` | 2 | Ändra | `/api/health` rapporterar även `klartex` |
| `backend/src/klartex_se/render_client.py` | 2 | Skapa | `render_pdf`, `RenderUpstreamError`, tidsbudget |
| `backend/Dockerfile` | 2 | Ändra | `python:3.12-slim`, healthcheck via urllib |
| `backend/tests/test_render.py` | 1, 2 | Ändra | Aliastester bort; proxy- och passthrough-tester |
| `backend/tests/test_render_client.py` | 2 | Skapa | `httpx.MockTransport`: statusar, headers, transportfel |
| `backend/tests/test_contract.py` | 2 | Skapa | `backend → klartex.server` i process |
| `backend/tests/test_page_templates.py` | 2 | Ändra | `load_bundle_payload`, trasiga bundles |
| `backend/README.md` | 1, 2 | Ändra | `page_template`-kontraktet, 502, slim-imagen |
| `llms.txt`, `index.html` | 1 | Ändra | Alias-namnen bort ur publika exempel |
| `infra/docker-compose.yml` | 2 | Ändra | `render` från kärnans image, internt nät, härdning, slutgiltiga tak |
| `infra/.env.example` | 2 | Ändra | `KLARTEX_VERSION`; `BACKEND_VERSION=0.6.0` |
| `infra/Caddyfile` | 2 | Ändra | `response_header_timeout` 180 s |
| `.github/workflows/deploy.yml` | 2 | Ändra | Tvåcontainer-smoke; båda `.env`-raderna; versionsjämförelse |
| `.github/workflows/ci.yml` | 2 | Ändra | `.env.example` == `pyproject.toml`-pinnen |
| `PLAN.md`, `CLAUDE.md` | 2 | Ändra | Beslutstabell, risktabell, kärnprincip 1 |

## Berörda kodområden

- `backend/` (src, tests, Dockerfile, README)
- `infra/` (compose, Caddyfile, .env.example, README)
- `.github/workflows/`
- `llms.txt`, `index.html`, `PLAN.md`, `CLAUDE.md`

## Designbeslut

> Varje beslut bär sin proveniens. Användarbesluten är fattade; agentens bedömningar är öppna att ifrågasätta.

### 1. Render-tjänsten är kärnans artefakt och versioneras som kärnan
**Beslut:** `swedev/klartex` bygger och publicerar `ghcr.io/swedev/klartex-render:<kärnversion>` vid varje release. klartex.se bygger den aldrig, pinnar den, och har en egen appversion.
**Motivering:** Det finns ingen kärnrelease som lämnar render-motorn orörd och ingen ändring i render-motorn som inte är en kärnrelease — två versionsserier i klartex.se skulle vara två namn på samma sak. Frågan "en eller två serier i klartex.se" upplöses därmed.
*Användarbeslut, konversation 2026-08-30. Kärnhalvan spåras i swedev/klartex#81.*

### 2. Aliasen `formal`/`clean`/`none` försvinner helt, även ur klartex.se:s publika API
**Beslut:** `page_template` blir `str | object` — sträng = registrerat bundle-namn, objekt = kärnans slot-form rakt igenom. `BUILTIN_PAGE_TEMPLATES` raderas; `llms.txt`, `index.html`, README- och `RenderRequest`-exempel rensas i PR 2a. Ingen mappning, ingen kvarlevande konvention.
**Motivering:** Kärnan tar bara `dict | None`. Att översätta namnen i klartex.se skulle bevara en konvention som inte finns någon annanstans, och `formal` i objektform kräver dessutom `org_name` och går bara att uttrycka som den bara varianten `"letterhead"` — en mappning skulle alltså inte ens vara trogen.
*Användarbeslut A, konversation 2026-08-30.*

### 3. En kärnrelease bär både alias-borttagningen och `klartex serve`
**Beslut:** klartex.se migrerar en gång, mot en release.
**Motivering:** Två migreringar mot två kärnreleaser vore två gånger arbetet och två fönster där repona kan glida isär.
*Användarbeslut B, konversation 2026-08-30. Kärn-issue: swedev/klartex#81.*

### 4. PR 0 körs direkt, före allt kärnberoende arbete
**Beslut:** Deploybarheten återställs innan något väntar på kärnan.
**Motivering:** `main` kan inte släppa en hotfix så länge compose kräver en variabel som inte finns på servern, och `pins`-jobbet blockerar pin-bumpen i PR 2a.
*Användarbeslut C, konversation 2026-08-30.*

### 5. Namnet `backend` behålls för app-tjänsten
**Alternativ:** A: byta namn på tjänst/katalog/image/env till `app` som issuet skriver, vs B: behålla `backend` och bara lägga till `render`.
**Beslut:** B.
**Motivering:** `app` är upptaget på tre ställen: frontend-katalogen `app/`, `~klartex/app` på servern och `/srv/app` i Caddyfile. Med B är katalog, image, env-variabel och tjänstenamn konsekventa, och Caddyfile och rollback-vägen rörs inte.
*Agentens bedömning, granskad — issuet använder `app` i prosan; namnet är öppet att ifrågasätta.*

### 6. Bundle-innehållet skickas inline per anrop, ingen delad volym
**Alternativ:** A: montera `./page-templates` read-only även i `render`, vs B: `backend` läser bundlen och skickar källa + assets (base64) i anropet.
**Beslut:** B.
**Motivering:** A ger render-tjänsten kännedom om registrets layout — som #19 ändrar — och en volym som issuet uttryckligen vill hålla borta från kompileringsprocessen. B gör tjänsten helt tillståndslös och ger samma kontrakt som #18 vill exponera publikt. Kostnaden är lokal trafik, hundratals kB i normalfallet.
*Agentens bedömning, granskad.*

### 7. Kärnan sätter felformerna, `backend` vidarebefordrar dem oförändrade
**Beslut:** `render` producerar `detail`-formerna; `backend` passar igenom status, `detail` och `Retry-After`, och lägger bara till `502 render_unavailable`.
**Motivering:** Felmappningen beror på kärnans meddelandeformer och hör hemma där kärnan anropas. Anslutningsfel och timeout får samma typ — klienten kan inte agera olika på dem.
*Agentens bedömning, granskad.*

### 8. `backend` behåller `klartex` som beroende
**Alternativ:** A: proxa även discovery så `backend` blir klartex-fritt, vs B: `backend` importerar `klartex` (utan TeX) för discovery och för `find_latex_block`s pinning mot kärnans carrier-block.
**Beslut:** B.
**Motivering:** `klartex` utan TeX Live väger några MB. Discovery-scheman är single source of truth och bör inte gå över nätet. Det som kostar är TeX-basen, och den lämnar `backend` oavsett.
*Agentens bedömning, granskad; följer CLAUDE.md:s kärnprincip 2.*

### 9. Resurstak: `render` 1792m / 1.5 CPU, `backend` 768m / 0.5 CPU
**Beslut:** Sätts i PR 2b; summan (2560m) är oförändrad mot `v0.5.0`, så OS, Docker och Caddy behåller samma marginal.
**Motivering:** `backend` får 768m för att två samtidiga bundle-payloads i värsta fall ska rymmas; in-flight-semaforen på 2 begränsar värsta fallet. CPU-taken summerar till 2,0 av 2 vCPU, och `backend` gör nästan inget CPU-arbete efter splitten. Siffran för `render` är **en uppskattning** och mäts med `docker stats` efter `v0.6.0`; taket justeras i en följdcommit. Postgres i #19 ryms inte i marginalen som den ser ut — antingen sänks `render` efter mätningen eller storleksändras värden till cax21.
*Agentens bedömning, granskad; issuet begär just den här kontrollen.*

### 10. `render` på internt nätverk, härdad container
**Beslut:** `internal: true`-nätverk utan gateway, plus `no-new-privileges`, `cap_drop: ALL`, `read_only: true`, tmpfs för `/tmp` och för `HOME`.
**Motivering:** Nätverket stänger den enda vägen ut för en process som kör anroparstyrd LaTeX: innehåll kan inte lämna containern annat än i den PDF `backend` returnerar. Härdningen kostar sex rader och tar bort privilegie-eskalering och skrivbar rootfs. `HOME` måste vara skrivbar eller tmpfs, annars klagar fontconfig per körning. Gate:as av deployens riktiga render-anrop: trippar `read_only`, släpp den raden och notera fallet under swedev/klartex#51. Filläsning *inom* containern kvarstår tills swedev/klartex#51.
*Agentens bedömning, granskad.*

### 11. Monolitiska bundlar skickas som `header_source` med `footer: null`
**Alternativ:** A: dela upp registrets bundle-format i slots direkt, vs B: en shim som översätter dagens monolitiska `page_template.tex.jinja` till kärnans slot-API.
**Beslut:** B i PR 2a; A är #64.
**Motivering:** Registret bär en enda `page_template.tex.jinja` och det finns inga per-slot-filer. Att skicka den som `header_source` med `footer: null` ger samma emission som en delad källa utan footer, alltså oförändrat resultat för befintliga bundlar. Bundlen vinner över ett anropar-skickat `footer`, vilket dokumenteras. Att ändra själva bundle-formatet är ett eget, större arbete.
*Agentens bedömning, granskad.*

### 12. Tre PR:er i denna ordning
**Beslut:** PR 0 (återställ deploybarhet, nu), PR 2a (kom ikapp kärnan, när releasen finns på PyPI), PR 2b (proxy + slim + konsumera imagen, när imagen finns på GHCR).
**Motivering:** PR 0 är oberoende av kärnan och löser ett akut problem på `main`. PR 2a behöver bara PyPI och kan därför öppnas så snart kärnreleasen är ute; att skilja den från 2b gör att det publika kontraktsbytet reviewas för sig. PR 2b är den som byter beteende i drift och kan rullas tillbaka till `v0.5.x` med `workflow_dispatch`.
*Agentens bedömning, granskad.*

## Verifieringschecklista

### PR 0
- [ ] `render/` finns inte; ingen fil utanför `agent-docs/` nämner `render-v`, `RENDER_VERSION`, `klartex-se-render` eller `render/`
- [ ] `docker compose config` validerar med bara `BACKEND_VERSION` satt och `API_TOKEN` osatt — inga andra variabler krävs
- [ ] `infra/docker-compose.yml` definierar `backend` och `caddy`, inga extra nätverk, `backend` på 2560m / 1.5 CPU
- [ ] `.github/workflows/deploy.yml` triggas bara av `v[0-9]+.[0-9]+.[0-9]+` och har jobben `build` och `deploy`
- [ ] `.github/workflows/ci.yml` har ett `test`-jobb utan matris och inget `pins`-jobb
- [ ] Båda workflow-filerna parsar som YAML
- [ ] `pytest` grönt i `backend/`

### PR 2a
- [ ] `pytest` grönt mot den nya kärn-pinnen; inget test refererar `formal`/`clean`/`none`
- [ ] `page_template` som objekt når kärnan oförändrat; som sträng slår upp bundlen; okänt namn → 400 `unknown_page_template`
- [ ] Shimmen skickar bundle-källan som `header_source` och sätter `data.page_template.footer = null`; en render med registrerad bundle ger samma PDF som före pin-bumpen
- [ ] `llms.txt`, `index.html`, `backend/README.md` och `RenderRequest`-exemplen är fria från alias-namnen
- [ ] `grep -r BUILTIN_PAGE_TEMPLATES backend/` ger inget

### PR 2b
- [ ] `backend`-tester: 403 för anonymt `latex`-block sker *före* proxy-anropet, upstream 400/503 passerar med status/detail/`Retry-After`, 422/HTML/ogiltig JSON och transportfel → 502 utan värdnamn i meddelandet, in-flight-semaforen ger 503, trasig bundle → 400
- [ ] Kontraktstestet grönt: `backend`s payload parsas av kärnans modell, kärnans `validation_error` med `path` når klienten oförändrad
- [ ] Tidsbudgeten sitter: `httpx.Timeout(connect=5, read=130, write=30, pool=5)`, `response_header_timeout 180s` i Caddyfile
- [ ] `docker build` av `backend/` ger en image under ~200 MB och installerar från `pyproject.toml`
- [ ] Lokal `docker compose up` med härdningen: `render` blir `healthy`, en riktig render ger PDF, och fontconfig loggar inte "No writable cache directories"
- [ ] `docker compose exec render env` visar ingen `API_TOKEN`; `curl -m 5 https://example.com` från `render` misslyckas
- [ ] `KLARTEX_VERSION` i `.env.example` är identisk med `klartex==`-pinnen i `backend/pyproject.toml`, och CI felar om de skiljer sig
- [ ] Deploy `v0.6.0` går grönt; `/api/health` rapporterar 0.6.0 och samma kärnversion som `render`s `version`; deployens render-anrop efter omstarten gav PDF
- [ ] `docker stats --no-stream` under en riktig rendering; taken justerade om det behövs
- [ ] `workflow_dispatch` från `v0.5.x` återställer monoliten och `--remove-orphans` städar render-containern
- [ ] Docs läser i nu-state: `backend/README.md`, `infra/README.md`, `PLAN.md`, `CLAUDE.md`
