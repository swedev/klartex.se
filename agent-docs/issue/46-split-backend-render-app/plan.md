# Plan: Issue #46 — Split the backend into a render service and an app service

## Mål

Dela dagens enda backend-container i två tjänster i samma compose-stack:

- **`render`** — en tillståndslös HTTP-inpackning av `klartex.render()`, byggd `FROM ghcr.io/swedev/klartex-base`, utan hemligheter i miljön, utan volymer, nåbar enbart på compose-nätverket. Byggs om när kärnan eller basen bumpas.
- **`backend`** (issuets "app") — dagens FastAPI-app minus kompileringen: discovery, auth/tier-policy, page-template-registret och all publik `/api`-trafik. Kompilering proxas till `render`. Det är hit Postgres, konton och parla (#19), dokumentpersistens och den anonyma nivån (#23) sedan läggs.

Resultatet ska vara osynligt för API-klienter: samma endpoints, samma felformer, samma Caddy-konfig utåt. Skillnaden är att processen som kör anroparstyrd LaTeX inte längre delar miljö med någon hemlighet, att ett produktrelease flyttar megabyte i stället för gigabyte, och att #19 kan byggas i rätt behållare från början.

## Triagering

> Beslutsunderlag för detta issue.

| Fält | Värde |
|------|-------|
| **Blockeras av** | Inget |
| **Blockerar** | #19 (konton/Postgres ska födas i `backend`, inte i TeX-containern), #47 (miljöexponeringen stängs av detta), #23 (payload-policyn i app-lagret) |
| **Relaterade issues** | #47, #19, #23, #39, #20, #18, #14, swedev/klartex#51 |
| **Omfattning** | ~22 filer i `backend/`, nytt `render/`, `infra/`, `.github/workflows/`, docs |
| **Risk** | Medel |
| **Komplexitet** | Medel |
| **Säker för junior** | Nej — produktionsutrullning i två steg, deploy-workflow och compose-topologi |
| **Konfliktrisk** | Låg — inga öppna planer rör samma filer aktivt; den omergade #14-grenen ändrar enbart `app/` |

### Triagemässiga noteringar

- **Inga blockerare.** swedev/klartex#51 (sandboxa xelatex i kärnan) är ett *alternativ* till den här splitten, inte en förutsättning; issuet är explicit med att splitten är det spår som finns nu. Båda kan landa — #51 skulle då härda `render` ytterligare.
- **Ordningen mot #19 är poängen.** Issuet argumenterar att Postgres/parla ska byggas in i `backend` *efter* splitten. #19 bör därför inte påbörjas förrän den här planens Fas 2 är mergad.
- **#47 stängs till hälften av #15 (0.5.0).** Det som återstår i #47 är miljöexponeringen i sig — exakt det `render` utan hemligheter löser. Planen bör stänga #47 (`Closes #46, closes #47` på PR 2) — verifiera vid PR-tillfället att inget nytt tillkommit i #47.
- **#18 (assets per anrop)** får sitt interna kontrakt gratis: `render`-tjänstens API tar bundle inline. Den publika varianten på `/api/render` är fortfarande #18:s sak.
- **#39 (releasebygget tar 8 min)** löses för produktreleaser: `backend`-imagen byggs på `python:3.12-slim` och flyttar aldrig TeX-basen. `render`-releaser behåller kostnaden, men de sker några gånger per år.
- **Minnesbudgeten på cax11 (4 GB)** ska kontrolleras innan taken sätts (issuet flaggar det). Splitten i sig ökar inte totalen, men Postgres i #19 får inte plats i marginalen utan att antingen `render`s tak sänks efter mätning eller värden storleksändras (cax21, 8 GB). Det ska stå som explicit förutsättning i #19. Se designbeslut 6.
- **GHCR-paketet `klartex-se-render` skapas av den första `render-v*`-körningen.** Repot är publikt och paket som publiceras av dess workflow ärver normalt synligheten, men det är inte garanterat. Servern pullar anonymt, så om paketet blir privat stannar `docker compose pull` — före omstarten, med stacken orörd. Åtgärden är då att sätta paketet publikt på `github.com/orgs/swedev/packages/container/klartex-se-render/settings` och köra om deployen via `workflow_dispatch` från taggen. Dokumenteras i `infra/README.md`.
- **Frontend-bygget** (issuets "and the frontend build" under `app`) ligger utanför: källan finns bara på #14-grenen och Caddy servar `~/app` statiskt idag. Hur frontenden paketeras avgörs när #14 landar; ingenting i den här planen låser det.

## Angreppssätt

### Vad som flyttar vart

Dagens `backend/src/klartex_se/render.py` innehåller två sorters kod som ska isär:

| Kod | Är | Hamnar i |
|-----|----|----------|
| `find_latex_block`, `_child_block_lists`, tier-kontrollen (403) | Policy — vad anroparen får göra | `backend` |
| `BUILTIN_PAGE_TEMPLATES`, bundle-uppslag mot registret (`get_bundle_path`) | Policy/lagring | `backend` |
| `_block_error_path`, `_BLOCK_ERROR_RE`, mappning `ValidationError`/`ValueError`/`RuntimeError` → 400/500 | Kärnnära — beror på kärnans meddelandeformer | `render` |
| `_render_slots`-semaforen (max 2 samtidiga, 503 `overloaded`) | Skydd av processen som kör xelatex | `render` |
| `klartex_render(...)`-anropet | Kompilering | `render` |

Discovery (`/api/templates`, `/api/blocks`, scheman) stannar i `backend`: det är rena Python-anrop mot `klartex`-paketet utan TeX, och `find_latex_block`s test pinnar sig mot kärnans `_child_block_lists`. `backend` behåller därför `klartex` som pip-beroende — men utan TeX-basen väger imagen några tiotal MB.

### Det interna kontraktet `backend → render`

`render` exponerar två endpoints, utan `/api`-prefix (den är intern):

- `GET /health` → `{"status": "ok", "version": "<render-version>"}`
- `POST /render` → `application/pdf` eller `{"detail": {...}}`

Request-kroppen speglar `klartex.render()`s signatur, med `asset_dir` ersatt av inline-filer:

```json
{
  "template": "_block",
  "data": {"lang": "sv", "body": [...]},
  "page_template_source": "<innehållet i page_template.tex.jinja eller null>",
  "assets": {"logo.pdf": "<base64>", "font.ttf": "<base64>"}
}
```

`render` skriver `assets` till en temporär katalog per anrop, anropar `klartex.render(template, data, page_template_source=..., asset_dir=tmp)` och städar. Inga volymer, inget tillstånd, ingen kännedom om registret. Filnamnen i `assets` valideras mot samma `ASSET_NAME_RE` som registret använder — `render` ska inte kunna fås att skriva utanför tempkatalogen ens av en felaktig `backend`.

Felsvaren från `render` har exakt samma `detail`-form som `/api/render` har idag (`validation_error` + `path`, `input_error` [+ `path`], `render_error`, `overloaded` + `Retry-After`). `backend` skickar dem vidare oförändrade med samma statuskod. Det enda nya i det publika kontraktet är `502 render_unavailable` — när `backend` inte når `render` eller anropet tar för lång tid.

### Sekvens i `backend`s `/api/render` efter splitten

1. Tier-kontroll: anonymt anrop med `latex`-block → 403 (oförändrat).
2. `page_template`: inbyggd → merga in i `data`; okänt namn (varken inbyggd eller registrerad) → 400 `unknown_page_template` (oförändrat). Bundlens *innehåll* läses först i steg 4, innanför semaforen.
3. Ta en av `MAX_INFLIGHT_RENDERS = 2` platser (icke-blockerande semafor, annars 503 `overloaded` + `Retry-After: 5`, samma form som `render`s). Samma tal som `render`s semafor: fler in-flight-anrop än så kan ändå bara vänta på ett 503 från `render`, och två är den övre gränsen för hur många bundle-payloads (~68 MB base64 i värsta fall, plus JSON-kopior) som byggs samtidigt i `backend`.
4. Bundle-namn → läs `page_template.tex.jinja` och alla assets ur registret, base64:a dem.
5. `POST {RENDER_URL}/render` med `httpx.Client(timeout=httpx.Timeout(connect=5, read=130, write=30, pool=5))`. Tidsbudgeten är uttalad och summerar även i värsta fall under proxyns tak: kärnans xelatex-tak är 2 × 60 s; `httpx` kan i värsta fall ta 5 + 30 + 130 = 165 s; Caddys `response_header_timeout` höjs från 150 s till **180 s** så att `backend` alltid hinner svara med ett strukturerat fel innan Caddy ger upp.
6. Svarshantering, i denna ordning:
   - 200 → PDF med `Content-Disposition` (oförändrat).
   - Status i {400, 500, 503} och en body vars `detail` är ett objekt med `type` och `message` → samma status, det inre `detail`-objektet oförändrat (aldrig `{"detail": {"detail": …}}`), och `Retry-After` vidarebefordrad om den finns. Inga andra headers passerar.
   - Allt annat (422 från pydantic i `render`, HTML, ogiltig JSON, oväntad status) → 502 `render_unavailable` med ett generiskt meddelande; `render`s svar loggas server-side.
   - `httpx.TransportError` (inklusive timeout) → 502 `render_unavailable`. Meddelandet nämner varken undantagstexten eller värdnamnet `render`.

### Två images, två versionsserier

`backend` och `render` byter takt: produktkod veckovis, TeX-miljön några gånger om året. En gemensam tagg skulle tvinga varje produktrelease att flytta 9 GB basimage genom CI igen (#39). Därför:

| | `backend` | `render` |
|---|---|---|
| Katalog | `backend/` | `render/` |
| Paket | `klartex_se` | `klartex_render` |
| Image | `ghcr.io/swedev/klartex-se-backend:<v>` | `ghcr.io/swedev/klartex-se-render:<v>` |
| Tagg | `v0.6.0` | `render-v0.1.0` |
| `.env` | `BACKEND_VERSION` | `RENDER_VERSION` |
| Bas | `python:3.12-slim` | `ghcr.io/swedev/klartex-base` (pinnad tagg + digest) |

`klartex`-pinnen ska vara identisk i båda `pyproject.toml` — discovery-scheman i `backend` och renderaren i `render` måste komma från samma kärnversion. Tre saker håller det sant:

- Båda `Dockerfile` installerar projektet från sin `pyproject.toml` (`COPY pyproject.toml src/ … && pip install .`) i stället för att upprepa beroendelistan, så pinnen finns på ett ställe per tjänst.
- CI kontrollerar med en rad att de två pinnarna är lika.
- Båda health-endpoints rapporterar den installerade kärnversionen (`"klartex": importlib.metadata.version("klartex")`; i `backend` läggs fältet till i `main.py` i PR 2). Deployen av `backend` jämför `backend`s och `render`s värden efter omstarten och fallerar vid skillnad; deployen av `render` skriver bara ut dem (under Fas 1 saknar monoliten fältet, vilket utskriften tål).

En kärnbump rullas alltid ut i ordningen `render` först, `backend` sedan. Fönstret däremellan är ofarligt: `render` validerar varje anrop mot *sin* kärnas schema, så en klient som byggt sitt dokument mot `backend`s äldre discovery-schema får det renderat av en nyare kärna, vilken är bakåtkompatibel inom samma major. Den farliga riktningen — `backend` nyare än `render`, där discovery erbjuder block som renderaren inte känner — är den deploy-kontrollen förhindrar. Bumpen är två taggar samma dag, ingen ceremoni utöver det.

### Utrullning i två steg

Compose-filen efter splitten refererar `${RENDER_VERSION:?}`. Den första deployen efter mergen måste därför vara `render-v0.1.0`: den skriver `RENDER_VERSION` till serverns `.env`, startar `render` bredvid den gamla monoliten (som fortsätter kompilera själv), och ingenting utåt ändras. Därefter `v0.6.0`, som byter `backend` till slim-imagen som proxar. Deployas i fel ordning stannar `docker compose pull` på den saknade variabeln — före omstarten, så den körande stacken rörs inte.

Rollback: `workflow_dispatch` från `v0.5.0` checkar ut det trädet, rsyncar dess compose-fil (utan `render`-tjänst) och startar om; `--remove-orphans` i systemd-uniten tar bort den föräldralösa `render`-containern.

## Steg

### Fas 1: `render`-tjänsten (PR 1)

1. Skapa `render/` som ett eget litet Python-projekt
   - `render/pyproject.toml`: namn `klartex-se-render`, version `0.1.0`, beroenden `klartex==0.15.0`, `fastapi`, `uvicorn[standard]`; dev: `pytest`, `httpx`
   - `render/src/klartex_render/__init__.py`: `__version__ = "0.1.0"`
   - `render/src/klartex_render/main.py`: FastAPI-app med `GET /health` (`status`, `version`, `klartex`) och `POST /render`; `docs_url=None`, `openapi_url=None`; en middleware som avvisar `Content-Length` över `MAX_REQUEST_BYTES` (~80 MB — största giltiga bundle i base64 plus data) med 413 innan kroppen läses
   - `render/src/klartex_render/render.py`: `RenderRequest` (`template`, `data`, `page_template_source: str | None`, `assets: dict[str, str]`), asset-validering (`ASSET_NAME_RE`, gräns per fil och antal — samma värden som registret; ogiltig base64 → 400 `input_error`), tempkatalog per anrop, semaforen `MAX_CONCURRENT_RENDERS = 2`, `_block_error_path` + `_BLOCK_ERROR_RE`, felmappningen från dagens `backend/src/klartex_se/render.py`
2. Kopiera de kärnnära testerna (de tas bort ur `backend/tests/` först i Fas 2, så monoliten förblir testad tills den byts)
   - `render/tests/test_render.py`: xelatex-beroende render-tester (`needs_xelatex`-skip som idag), `_block_error_path`-enhetstester, `detail.path`-tester, semafortester, asset-tester (bundle med logotyp renderar; ogiltigt filnamn → 400; ogiltig base64 → 400; för stor asset → 400; för stor `Content-Length` → 413). Utgå från dagens `backend/tests/test_render.py`.
3. `render/Dockerfile`
   - Dagens `backend/Dockerfile` med `klartex_render.main:app`, samma `FROM`-pin, `COPY pyproject.toml src/` + `pip install --no-cache-dir .` i venvet, samma `HEALTHCHECK` mot `http://localhost:8000/health`
4. `render/README.md` (svenska): syfte, kontraktet ovan, lokal körning (`uvicorn klartex_render.main:app --port 8001`), att den aldrig ska exponeras publikt
5. Compose och deploy för `render`
   - `infra/docker-compose.yml`: ny tjänst `render` (image `ghcr.io/swedev/klartex-se-render:${RENDER_VERSION:?…}`, inga `ports`, inga volymer, ingen `environment`, resurstak enligt designbeslut 6, healthcheck, `restart: unless-stopped`); nätverket `render` med `internal: true`; `backend` läggs på både `default` och `render`. Taken i PR 1 är övergångsvärden: `render` 1536m och monoliten `backend` sänkt från 2560m till 1792m, så att summan (3328m) ryms under värdens 4 GB med marginal för OS, Docker och Caddy medan båda kan kompilera. PR 2 sätter slutvärdena (designbeslut 6)
   - `infra/.env.example`: `RENDER_VERSION=0.1.0` med kommentar om versionsserien
   - `.github/workflows/deploy.yml`: trigger på `render-v[0-9]+.[0-9]+.[0-9]+` utöver `v…`; nytt jobb `resolve` som ur taggen härleder `service` (`backend`/`render`), `version`, `context`, `image`, `env_var` och verifierar mot rätt `pyproject.toml`; `build` och `deploy` parametriseras på dess outputs. Smoke-testet för `render`: `GET /health` + `POST /render` → PDF (dagens test med ny path). Deploy-steget skriver bara `${env_var}=${version}` i `.env`, `docker compose ps`-kontrollen omfattar `backend render caddy`, och versionsverifieringen för `render` går via `docker compose exec -T render curl -fsS http://localhost:8000/health` (porten är inte publicerad) följt av en riktig render (`POST /render` med minimal `_block`-body → `%PDF`) medan `restore`-trappen fortfarande är armerad. Health-utskriften visar båda tjänsternas `klartex`-version
   - `.github/workflows/ci.yml`: matris över `backend` och `render` (`pip install -e '.[dev]' && pytest -q -rs` i respektive katalog) plus ett steg som kontrollerar att `klartex==`-pinnen är identisk i båda `pyproject.toml`
6. `infra/README.md`: tabellraden för `docker-compose.yml`, avsnittet "Uppgradera" får ett stycke om `render-v*`-serien, felsökningens `logs`-exempel

**PR 1 är deploybar och ofarlig:** `render-v0.1.0` startar en tjänst ingen anropar än.

### Fas 2: `backend` blir policy-lagret (PR 2)

1. `backend/src/klartex_se/render_client.py` (ny)
   - `RENDER_URL = os.environ.get("RENDER_URL", "http://render:8000")`
   - `class RenderUpstreamError(Exception)` med `status_code`, `detail`, `headers`
   - `render_pdf(template, data, page_template_source, assets) -> bytes` med en modulglobal `httpx.Client` och tidsbudgeten från Angreppssätt (connect 5 / read 130 / write 30 / pool 5). Svarsalgoritmen exakt som i Angreppssätt: 200 → bytes; {400, 500, 503} med validerat `detail`-objekt → `RenderUpstreamError(status, detail, {"Retry-After": …} om satt)`; allt annat och alla `httpx.TransportError` → `RenderUpstreamError(502, {"type": "render_unavailable", "message": "The render service did not answer. Retry in a few seconds."})` med `log.warning` som bär status och början av kroppen
   - Klienten byggs så att den går att ersätta i test: `httpx.Client(transport=…)` via en modulfunktion `_client()` som tester kan monkeypatcha
2. `backend/src/klartex_se/render.py`
   - Ta bort `_block_error_path`, `_BLOCK_ERROR_RE` och importen av `klartex.render`; semaforen blir `MAX_INFLIGHT_RENDERS = 2` och tas *före* bundle-laddningen så att den täcker både payload-bygget och proxy-anropet, med samma 503 `overloaded` som idag
   - Bundle-grenen läser `page_template.tex.jinja` plus alla filer i `asset_names` ur metadata och base64:ar dem (hjälpare `load_bundle_payload(name) -> tuple[str, dict[str, str]]` i `page_templates.py`; en asset som saknas på disk eller en template-källa som inte är giltig UTF-8 ger `PageTemplateError` → 400 `input_error`, eftersom bundlen då är trasig, inte anropet)
   - Anropa `render_pdf`; `except RenderUpstreamError as e: raise HTTPException(e.status_code, detail=e.detail, headers=e.headers)`
   - `responses`-dokumentationen: 502 tillkommer; 503 beskriver `overloaded` som antingen `backend`s eller `render`s
3. `backend/pyproject.toml` + `__init__.py`: version `0.6.0`; `httpx>=0.27` flyttas från dev till huvudberoenden
4. `backend/Dockerfile`
   - `FROM python:3.12-slim`; venv med `klartex`, `fastapi`, `uvicorn`, `httpx`, `python-multipart`; `HEALTHCHECK` via `python -c "import urllib.request; …"` (slim har ingen curl — samma mönster som styrlas compose)
5. `backend/tests/test_render.py`
   - `fake_render`-fixturen monkeypatchar `render_module.render_pdf` i stället för `klartex_render`; ta bort de tester som kopierades till `render/tests/` i Fas 1; behåll tier-/403-/`find_latex_block`-/carrier-pinning-testerna; nya tester: 403 för `latex` sker utan att `render_pdf` anropas, bundle-payload byggs rätt (`page_template_source` + `assets`), inbyggd sidmall mergas in i `data`, `RenderUpstreamError` 400/503 passerar med status, `detail` och `Retry-After`, in-flight-semaforen ger 503 vid full, transportfel → 502 `render_unavailable`
   - `backend/tests/test_render_client.py` (ny): `render_pdf` mot en `httpx.MockTransport` — 200 → bytes, 400 med `detail` → `RenderUpstreamError(400)`, 503 med `Retry-After` → header vidarebefordrad, 422/HTML/ogiltig JSON/okänd status → 502, `httpx.ConnectError`/`ReadTimeout` → 502, meddelandet innehåller inte värdnamnet
   - `backend/tests/test_contract.py` (ny): kontraktstest end-to-end i process — `_client()` monkeypatchas till `starlette.testclient.TestClient(klartex_render.main.app)`, som är en synkron `httpx.Client`-subklass med egen transport och tar absoluta URL:er oavsett värdnamn, så att `backend`s payload verkligen parsas av `render`s pydantic-modell och `render`s felform verkligen passerar `backend`s validering. Utan xelatex täcks `validation_error`/`input_error` med `path` och asset-valideringen; med xelatex även en riktig PDF. Kräver att `render` är installerat i `backend`s testmiljö (CI: `pip install -e ../render` i backend-jobbet — billigt, ingen TeX)
   - `backend/tests/test_page_templates.py`: nya enhetstester för `load_bundle_payload` — normal bundle, asset som saknas på disk, template-källa som inte är UTF-8, bundle som tas bort mellan `get_bundle_path` och läsning (→ `PageTemplateNotFound`)
6. `infra/docker-compose.yml`: `backend` får `RENDER_URL` (dokumenterande — defaulten gäller), `depends_on: render: condition: service_healthy`, sänkta tak (designbeslut 6); volymen `./page-templates` ligger kvar enbart på `backend`. **Compose-healthchecken för `backend` byts** från `curl` till samma `python -c "import urllib.request; …"` som imagen — compose-nivåns `healthcheck:` åsidosätter imagens, och slim-imagen har ingen curl, så utan bytet blir `backend` aldrig `healthy` och Caddy startar inte
7. `.github/workflows/deploy.yml`: smoke-testet för `backend` körs som en tvåcontainer-stack — `render` pullas på den version `infra/.env.example` pinnar (`RENDER_VERSION`), `backend` är den nybyggda imagen, båda på ett tillfälligt Docker-nätverk — och kör `GET /api/health`, `GET /api/templates` innehåller `_block`, `POST /api/render` med `latex`-block → 403, `POST /api/render` med minimal `_block`-body → `%PDF` (hela kedjan `backend → render → xelatex`), och kontrollerar att `klartex`-versionen i båda health-svaren är lika. Pullen av `render`-imagen kostar ~2 min per `backend`-release; det är release-tid och accepterat. Efter omstarten på servern gör deployen samma render-anrop mot `127.0.0.1:8000/api/render` innan `restore`-trappen släpps
8. `infra/Caddyfile`: `response_header_timeout` 150 s → 180 s, kommentaren bär tidsbudgeten (xelatex 2 × 60 s → httpx värsta fall 165 s → Caddy 180 s)

### Fas 3: Dokumentation i nu-state (i PR 2)

1. `backend/README.md`: inledningen beskriver rollen som policy-lager; endpoint-tabellen oförändrad; felsvarstabellen får `render_unavailable` 502 och `overloaded` beskrivs som `render`s svar; "Belastningstak"-avsnittet pekar på `render`; Docker-avsnittet beskriver slim-imagen; "Bumpa basimagen" flyttar till `render/README.md`; lokal utveckling visar `RENDER_URL=http://localhost:8001` mot en lokalt startad render
2. `infra/README.md`: "Vad ligger var", "Från noll till live" (`.env` bär två versioner), "Uppgradera" (två serier, utrullningsordningen efter splitten), "Rate limit"-avsnittet (taken sitter nu på `render`), "Säkerhet" (render har inga hemligheter, inget nätverk utåt, ingen publicerad port)
3. `PLAN.md`: raden **API-image** i beslutstabellen (två images, två serier), **Hosting**-raden (fyra containrar när Postgres kommer), risktabellens rad om `/api/render` (kompileringen kör utan hemligheter i miljön och utan nätverk; filläsning inom containern kvarstår tills swedev/klartex#51)
4. `CLAUDE.md`: kärnprincip punkt 1 nämner `render/` som den enda platsen som anropar `klartex.render()`; tabellen "Relaterade repon" oförändrad

### Fas 4: Utrullning

1. Merga PR 1 → tagga `render-v0.1.0`. Stannar `docker compose pull` på paketets synlighet: sätt `klartex-se-render` publikt och kör om via `workflow_dispatch` (se triagenoteringen). Verifiera i deploy-loggen att `render` är `healthy`, att dess interna render gav PDF och att `/api/render` fortfarande svarar (monoliten kompilerar än)
2. **Mät innan PR 2 mergas:** med `render-v0.1.0` i produktion, kör två samtidiga renders mot `render` (via `docker compose exec`) och läs `docker stats` — det avgör om 1792m i designbeslut 6 håller eller ska justeras i PR 2, inte efteråt. Kör mätningen under en lugn stund: monoliten kan kompilera samtidigt, och övergångstaken i PR 1 är satta för att båda ska rymmas
3. Merga PR 2 → tagga `v0.6.0` → verifiera `curl -fsS https://app.klartex.se/api/health` rapporterar `0.6.0` och samma `klartex` som `render`, en render med inbyggd sidmall ger PDF, en render med registrerad bundle (t.ex. `vkf`) ger PDF med logotyp, ett anonymt `latex`-block ger 403
4. Kontrollera på servern att `render`-containerns miljö saknar `API_TOKEN` (`docker compose exec render env`) — det är hela poängen med #47 — och att `docker compose exec render curl -m 5 https://example.com` misslyckas
5. Uppdatera #19 med att `backend` är platsen för Postgres/parla och att minnesmarginalen (designbeslut 6) är en förutsättning där; stäng #47 via PR 2:s `Closes`

## Filöversikt

| Fil | Åtgärd | Syfte |
|-----|--------|-------|
| `render/pyproject.toml` | Skapa | `klartex-se-render` 0.1.0; samma `klartex`-pin som backend |
| `render/src/klartex_render/__init__.py` | Skapa | `__version__` |
| `render/src/klartex_render/main.py` | Skapa | FastAPI-app: `GET /health`, `POST /render`; inga docs |
| `render/src/klartex_render/render.py` | Skapa | Inline-assets → tempkatalog, `klartex.render`, semafor, felmappning (`_block_error_path` flyttar hit) |
| `render/tests/test_render.py` | Skapa | Kärnnära tester flyttade från `backend/tests/` + asset-/kontraktstester |
| `render/Dockerfile` | Skapa | Dagens backend-Dockerfile på `klartex-base`, ny app-modul |
| `render/README.md` | Skapa | Kontrakt, lokal körning, basimage-bump |
| `backend/src/klartex_se/render_client.py` | Skapa | `render_pdf`, `RenderUpstreamError`, `RENDER_URL`, `_client()` med tidsbudgeten |
| `backend/src/klartex_se/main.py` | Ändra | `/api/health` rapporterar även `klartex` (installerad kärnversion) |
| `backend/src/klartex_se/render.py` | Ändra | Policy + bundle-payload + proxy; kompilering, semafor och felmappning bort |
| `backend/src/klartex_se/page_templates.py` | Ändra | `load_bundle_payload(name)` — template-källa + assets som base64 |
| `backend/pyproject.toml`, `backend/src/klartex_se/__init__.py` | Ändra | 0.6.0; `httpx` som huvudberoende |
| `backend/Dockerfile` | Ändra | `FROM python:3.12-slim`; healthcheck via urllib |
| `backend/tests/test_render.py` | Ändra | `fake_render` → `render_pdf`; in-flight-semafor, upstream-passthrough- och 502-tester; xelatex-tester bort |
| `backend/tests/test_render_client.py` | Skapa | `render_pdf` mot `httpx.MockTransport`: statusar, headers, trasiga svar, transportfel |
| `backend/tests/test_contract.py` | Skapa | Kontraktstest `backend → render` i process via Starlettes `TestClient` som `_client()` |
| `backend/tests/test_page_templates.py` | Ändra | Enhetstester för `load_bundle_payload` inklusive trasiga bundles |
| `backend/README.md` | Ändra | Roll, felsvarstabell (502), belastningstak, Docker, lokal utveckling |
| `infra/docker-compose.yml` | Ändra | Tjänst `render` (intern, utan hemligheter/portar/volymer), nätverk `render` (`internal: true`), `RENDER_VERSION`, `depends_on`, nya resurstak |
| `infra/.env.example` | Ändra | `RENDER_VERSION`; `BACKEND_VERSION=0.6.0` |
| `infra/Caddyfile` | Ändra | `response_header_timeout` 150 s → 180 s med tidsbudgeten i kommentaren; proxar fortfarande `backend:8000` |
| `infra/README.md` | Ändra | Två tjänster, två versionsserier, utrullningsordning, säkerhetsavsnitt |
| `.github/workflows/deploy.yml` | Ändra | `render-v*`-trigger; `resolve`-jobb; parametriserat bygge/smoke/deploy; verifiering av båda tjänsterna |
| `.github/workflows/ci.yml` | Ändra | Matris `backend`/`render`; backend-jobbet installerar även `../render` för kontraktstestet; pin-likhetskontroll |
| `PLAN.md` | Ändra | Beslutstabell (API-image, hosting) och risktabell i nu-state |
| `CLAUDE.md` | Ändra | Kärnprincip 1: `render/` kompilerar, `backend/` är policy |

Oförändrade men värda att nämna: `infra/cloud-init.yaml`, `llms.txt`, `index.html` (det publika API:t ändras inte).

## Berörda kodområden

- `backend/` (src, tests, Dockerfile, README)
- `render/` (nytt)
- `infra/` (compose, .env.example, README)
- `.github/workflows/`
- `PLAN.md`, `CLAUDE.md`

## Designbeslut

> Icke-triviala val gjorda under planeringen. Feedback välkommen; annars implementeras enligt dessa.

### 1. Namn: `backend` behålls för app-tjänsten, `render` är ny
**Alternativ:** A: byta namn på tjänst/katalog/image/env till `app` som issuet skriver, vs B: behålla `backend` överallt och bara lägga till `render`.
**Beslut:** B.
**Motivering:** `app` är redan upptaget på tre ställen: frontend-katalogen `app/` (PLAN.md:s beslut, #14-grenen), `~klartex/app` på servern och `/srv/app` i Caddyfile — alla frontend-dist. En compose-tjänst `app` bredvid dem skulle förvirra. Med B är katalog, image, env-variabel och tjänstenamn konsekventa (`backend/` ↔ `klartex-se-backend` ↔ `BACKEND_VERSION` ↔ `backend:8000`), Caddyfile och rollback-vägen rörs inte, och issuets "app" ↔ `backend` i detta repo. *Agentens bedömning — issuet använder `app` i prosan; namnet är öppet att ifrågasätta.*

### 2. Assets skickas inline per anrop, ingen delad volym
**Alternativ:** A: montera `./page-templates` read-only även i `render` och skicka bundle-namn, vs B: `backend` läser bundlen och skickar `page_template_source` + `assets` (base64) i anropet.
**Beslut:** B.
**Motivering:** A ger `render` kännedom om registrets layout — som #19 ändrar (per org) — och en volym som just issuet vill hålla borta från kompileringsprocessen. B gör `render` helt tillståndslöst och ger samma kontrakt som #18 vill exponera publikt. Kostnaden är att bundle-bytes (normalt hundratals kB, max ~51 MB) går över compose-nätverket per anrop; det är lokal trafik och acceptabelt för MVP-volymer. *Agentens bedömning; följer issuets "stateless wrapper" och #18.*

### 3. `render` sätter felformerna, `backend` vidarebefordrar dem oförändrade
**Alternativ:** A: `render` ger råa fel och `backend` tolkar om, vs B: `render` producerar exakt dagens `detail`-form och `backend` passar igenom status, `detail` och `Retry-After`.
**Beslut:** B.
**Motivering:** Felmappningen (`_block_error_path`) beror på kärnans meddelandeformer och hör hemma där kärnan anropas. Det publika kontraktet i `backend/README.md` förblir därmed identiskt utom ett tillägg: `502 render_unavailable` vid anslutningsfel/timeout mot `render`. Anslutningsfel och timeout får samma typ — klienten kan inte agera olika på dem. *Agentens bedömning.*

### 4. `backend` behåller `klartex` som beroende
**Alternativ:** A: proxa även discovery till `render` så `backend` blir TeX- och klartex-fritt, vs B: `backend` importerar `klartex` (utan TeX) för discovery och för `find_latex_block`s pinning mot kärnans carrier-block.
**Beslut:** B.
**Motivering:** `klartex` utan TeX Live väger några MB och drar inga tunga beroenden; discovery-scheman är single source of truth och bör inte gå över nätet. Det som kostar är TeX-basen, och den lämnar `backend` oavsett. Priset är att båda tjänsterna måste pinna samma `klartex`-version; CI kontrollerar det med en rad. *Agentens bedömning; följer CLAUDE.md:s kärnprincip 2.*

### 5. Två versionsserier och två taggmönster i samma workflow
**Alternativ:** A: en `v*`-tagg bygger båda images, vs B: `v*` → `backend`, `render-v*` → `render`, med ett `resolve`-jobb som parametriserar resten av `deploy.yml`.
**Beslut:** B.
**Motivering:** Hela poängen med cadence-argumentet i issuet är att en produktrelease inte ska flytta TeX-basen; A skulle behålla #39:s 8 minuter per release. B ger två oberoende serier med minimal ceremoni — en tagg per release, som idag — och en workflow-fil utan duplicerade SSH-steg. `concurrency: production-deploy` delas så två deployer aldrig interfolieras. *Agentens bedömning.*

### 6. Resurstak: `render` 1792m / 1.5 CPU, `backend` 768m / 0.5 CPU
**Alternativ:** Behålla 2560m på den tjänst som kompilerar, vs sänka.
**Beslut:** Slutvärden i PR 2 — `render`: `mem_limit`/`memswap_limit` 1792m, `cpus 1.5`, `pids_limit 256`; `backend`: 768m/768m, `cpus 0.5`, `pids_limit 128`. Övergångsvärden i PR 1 (monoliten kompilerar än): `backend` 1792m, `render` 1536m.
**Motivering:** Slutsumman (2560m) är oförändrad mot idag, så OS, Docker och Caddy behåller exakt den marginal de har nu (~1,5 GB på cax11:s 4 GB). `backend` får 768m för att två samtidiga bundle-payloads i värsta fall (~68 MB base64 vardera plus JSON-kopior) ska rymmas med marginal; in-flight-semaforen på 2 är det som gör värsta fallet begränsat. CPU-taken summerar till 2,0 av 2 vCPU; `backend` gör nästan inget CPU-arbete efter splitten, så Caddy konkurrerar i praktiken bara med `render`. Två samtidiga xelatex-körningar ligger normalt långt under 1 GB, så 1792m är sannolikt generöst — men **siffran är en uppskattning** och mäts i Fas 4 steg 2 innan PR 2 mergas. Postgres i #19 ryms *inte* i marginalen som den ser ut: antingen sänks `render` efter mätningen (t.ex. till 1280m) eller så storleksändras värden till cax21 (8 GB) — det avgörs i #19, inte här. *Agentens bedömning; issuet begär just den här kontrollen.*

### 7. `render` på ett internt nätverk utan egress
**Alternativ:** Bara utelämna `ports:`, vs dessutom lägga `render` på ett compose-nätverk med `internal: true`.
**Beslut:** Internt nätverk.
**Motivering:** Kostar tre rader i compose-filen och stänger den enda vägen ut för en process som kör anroparstyrd LaTeX: filläsning inom containern kvarstår tills swedev/klartex#51, men innehållet kan inte lämna containern annat än i den PDF `backend` returnerar. `render` behöver inget utåt (fonter och paket är lokala). *Agentens bedömning; bör nämnas i infra/README:s säkerhetsavsnitt.* `read_only: true` + tmpfs för `render` övervägdes men lämnas utanför — fontconfig-cachen gör det osäkert utan test på riktig image.

### 8. Två PR:er, i utrullningsordning
**Alternativ:** En PR, vs PR 1 (`render` + infra/CI för den) och PR 2 (`backend` proxar + docs).
**Beslut:** Två.
**Motivering:** PR 1 är deploybar utan att ändra något utåt, vilket gör att `render-v0.1.0` kan ligga i produktion och verifieras innan `backend` börjar bero på den. PR 2 är den som byter beteende och kan rullas tillbaka till `v0.5.0` med `workflow_dispatch`. PR 2 bär `Closes #46, closes #47`. *Agentens bedömning.*

## Verifieringschecklista

- [ ] `pytest` grönt i både `backend/` och `render/` utan xelatex (xelatex-tester skippas, som i CI)
- [ ] `render`-tester med xelatex lokalt: minimal `_block`-render, bundle med asset renderar med logotyp, `detail.path` på blockfel, semaforen ger 503 + `Retry-After`
- [ ] `backend`-tester: 403 för anonymt `latex`-block körs *före* proxy-anropet (ingen `render_pdf`-call), upstream 400/503 passerar med status/detail/headers, 422/HTML/ogiltig JSON och transportfel → 502 `render_unavailable` utan värdnamn i meddelandet, in-flight-semaforen ger 503, bundle-payload innehåller template-källa och alla assets, trasig bundle → 400
- [ ] Kontraktstestet (`test_contract.py`) grönt: `backend`s payload parsas av `render`s modell, `render`s `validation_error` med `path` når klienten oförändrad
- [ ] Tidsbudgeten sitter: `httpx.Timeout(connect=5, read=130, write=30, pool=5)` i klienten (värsta fall 165 s), `response_header_timeout 180s` i Caddyfile
- [ ] Maxlasttest lokalt i compose med slutgiltiga tak: en bundle med 10 assets à 5 MB renderas två gånger samtidigt plus ett tredje anrop → 200/200/503, ingen OOM-kill i `docker events`, `backend` under 768m i `docker stats`
- [ ] `docker build` av `render/` producerar en image med samma storlek som dagens backend-image; `docker build` av `backend/` ger en image under ~200 MB; båda installerar från `pyproject.toml` (ingen beroendelista i `Dockerfile`)
- [ ] Compose-healthchecken för `backend` använder `python -c "import urllib.request; …"` och tjänsten blir `healthy` i en lokal `docker compose up`
- [ ] `docker compose config` validerar; `render` saknar `ports`, `volumes` och `environment`; `docker compose exec render env` visar ingen `API_TOKEN`
- [ ] Från `render`-containern: `curl -m 5 https://example.com` misslyckas (internt nätverk); från `backend` (ingen curl i slim): `python -c "import urllib.request; print(urllib.request.urlopen('http://render:8000/health', timeout=5).read())"` lyckas
- [ ] Deploy `render-v0.1.0` går grönt (paketet `klartex-se-render` är publikt); deployens interna render mot `render` gav PDF; `/api/render` fungerar oförändrat under tiden monoliten kör
- [ ] `docker stats` med två samtidiga renders mot `render` i produktion, innan PR 2 mergas — tak justerat i PR 2 om det behövs
- [ ] `backend`-releasens smoke-test kör hela kedjan `backend → render → xelatex` och jämför `klartex`-versionerna
- [ ] Deploy `v0.6.0` går grönt; `/api/health` rapporterar 0.6.0 och samma `klartex` som `render`; deployens render-anrop efter omstarten gav PDF; render med inbyggd sidmall, med registrerad bundle och med anonymt `latex`-block ger 200/200/403
- [ ] Felordning: en deploy av `v0.6.0` mot en `.env` utan `RENDER_VERSION` stannar vid `docker compose pull` med stacken orörd (testas på en kopia av `.env` lokalt eller genom att läsa workflow-logiken — inte mot prod)
- [ ] `workflow_dispatch` från `v0.5.0` återställer monoliten (rollback-väg dokumenterad, helst testad på servern efter lyckad utrullning)
- [ ] Docs läser i nu-state: `backend/README.md`, `render/README.md`, `infra/README.md`, `PLAN.md`, `CLAUDE.md`
