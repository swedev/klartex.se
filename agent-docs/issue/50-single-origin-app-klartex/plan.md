# Plan: Issue #50 — Single origin: serve the webapp and the API from app.klartex.se, retire api.klartex.se

## Mål

Flytta hela API-ytan till `https://app.klartex.se/api/...` och ta bort `api.klartex.se` helt. Backend monterar alla routes under `/api`, Caddy servar frontend-bundlen och proxar `/api` till backend-containern på samma vhost, CORS-blocket försvinner, CSP krymper till `connect-src 'self'`, och allt innehåll (`llms.txt`, `index.html`, `infra/README.md`, `PLAN.md`) pekar om till den nya adressen. Ingen deprecation-alias — `api.klartex.se` tas bort direkt (användarbeslut, se issuens Provenance).

## Triagering

> Beslutsunderlag för detta issue.

| Fält | Värde |
|------|-------|
| **Blockeras av** | Inget |
| **Blockerar** | #14 (frontend skrivs mot relativa `/api/...` från start), #19 (auth föds same-origin) |
| **Relaterade issues** | #21, #23 (dokumenterar en URL-rymd i stället för två), #46 (framtida app/render-split ändrar vad som står bakom `/api`, inte adressen) |
| **Omfattning** | ~20 filer i `backend/`, `infra/`, `.github/workflows/`, repo-roten |
| **Risk** | Medel |
| **Komplexitet** | Medel |
| **Säker för junior** | Nej |
| **Konfliktrisk** | Medel — öppna PR #45 (`issue/21-svensk-startsida`) skriver om `index.html`; landar #45 först görs ompekningen i den nya texten, landar detta först behöver #45 rebasas. Planen för #20 (öppet) rör också `infra/Caddyfile`, `infra/README.md` och `.github/workflows/deploy.yml`, men dess ändringar ser ut att redan vara landade (rate limit-zonen och caddy-bygget finns i trädet). Plan #17 rörde `llms.txt`/`index.html` men #17 är stängt. |

### Triagemässiga noteringar

- Inga blockerare. Issuet ska tvärtom landa **före** #14 och #19 — det är hela poängen med tajmingen: API:et är dagar gammalt och enda kända konsumenten är detta repo.
- Ändringen är URL-brytande för externa konsumenter av `api.klartex.se`, men issuet fastslår att inga sådana finns utöver det vi själva kontrollerar (`llms.txt` styr agenttrafiken).
- Två åtgärder ligger utanför detta repo och kan inte utföras här: DNS-posten för `api.klartex.se` droppas hos Loopia (manuellt användarsteg), och parla-katalogens `services.toml` (`swedev/parla`) byts till `api_base_url = "https://app.klartex.se"`. Båda listas i verifieringschecklistan som uppföljningar.
- #46 (app/render-split) ritar om backend-topologin senare, men `/api`-prefixet och Caddy-strukturen från detta issue är precis den form #46 bygger vidare på — ingen konflikt, bara sekvens.
- Cutover-ordning: repo-ändringarna deployas och verifieras **innan** DNS-posten droppas och parla-katalogen byts. `api.klartex.se` slutar svara redan när nya Caddyfilen deployas (vhosten är borta), vilket är acceptabelt per issuet — men rollback efter DNS-droppen kräver att DNS-posten återskapas, inte bara att v0.3.0 deployas om. Se Fas 5.

## Angreppssätt

Dagens uppsättning har tre vhosts i `infra/Caddyfile`: landningssidan (`klartex.se`), frontend (`app.klartex.se`, statiska filer) och API (`api.klartex.se`, reverse proxy till `backend:8000` med handrullad CORS-preflight, body-tak och rate limit på `POST /render`). Backend (`backend/src/klartex_se/main.py`) monterar routers utan prefix: `/health`, `/templates`, `/blocks`, `/page-templates`, `/render`.

Syskontjänsterna (styrla m.fl.) kör en origin: en vhost, `/api`-prefix i URL-rymden, ingen CORS någonstans (`~/repos/styrla/infra/Caddyfile` är en enrads `reverse_proxy`; Vite proxar `/api` i dev). klartex följer samma mönster, med den skillnaden att frontend här är en statisk Vite-bundle som Caddy servar direkt — så `app.klartex.se`-vhosten blir `handle /api/*` → proxy till backend, resten → `file_server` med SPA-fallback.

Nyckelvalet är att prefixet läggs **i backend**, inte som strip i Caddy: backend svarar själv på `/api/health`, `/api/render`, osv. Då är dev- och prod-paths identiska (Vite proxar `/api` rakt av utan rewrite när #14 byggs) och kontraktet syns i URL:en, precis som issuet kräver. Caddy proxar `/api/*` utan att röra pathen.

Allt som pekar på gamla paths följer med i samma PR: compose-healthcheck, deploy-workflowens smoke test och versionsverifiering, backend-tester, README-exempel, `llms.txt`, `index.html`, `PLAN.md`:s domängräns-rad. Caddyfilen och backend-imagen deployas i samma körning (deploy-workflowen rsyncar config och byter `BACKEND_VERSION` i samma steg), så det uppstår ingen period där Caddy och backend talar olika URL-rymder.

## Steg

### Fas 1: Backend — montera allt under `/api`

1. Prefixa alla routes med `/api` i `backend/src/klartex_se/main.py`
   - Skapa en samlande `APIRouter(prefix="/api")`, inkludera `discovery_router`, `page_template_router`, `render_router` i den, och inkludera den i appen.
   - Flytta `GET /health` in under samma prefix → `GET /api/health` (issuet fastslår verifierings-URL:en `https://app.klartex.se/api/health`).
   - Sätt `docs_url="/api/docs"`, `openapi_url="/api/openapi.json"`, `redoc_url=None`, `swagger_ui_oauth2_redirect_url="/api/docs/oauth2-redirect"` i `FastAPI(...)` så OpenAPI-ytan förblir nåbar genom proxyn och ingen route blir kvar utanför `/api` (utan redirect-argumentet behåller FastAPI `/docs/oauth2-redirect` på roten; se designbeslut 3).
   - Filer att ändra: `backend/src/klartex_se/main.py`
2. Uppdatera testerna till de nya pathsen
   - Alla `client.get/post/delete("/...")` → `"/api/..."` i `test_discovery.py`, `test_page_templates.py`, `test_render.py`.
   - Nytt invariant-test: ingen route i `app.routes` ligger utanför `/api` (fångar en framtida route som glömmer prefixet).
   - Filer att ändra: `backend/tests/test_discovery.py`, `backend/tests/test_page_templates.py`, `backend/tests/test_render.py`
3. Versionsbump 0.3.0 → 0.4.0 (path-brytande API-ändring)
   - Filer att ändra: `backend/pyproject.toml`, `backend/src/klartex_se/__init__.py`
4. Uppdatera backend-dokumentation och path-referenser i kod
   - Endpoint-tabellen och curl-exemplen (`http://localhost:8000/api/...`) i `backend/README.md`.
   - `HEALTHCHECK`-raden i `backend/Dockerfile` → `http://localhost:8000/api/health`.
   - Field-beskrivningen "see /page-templates" i `render.py` → `/api/page-templates`; docstringen i `auth.py` refererar `/page-templates` och `/render`; svep docstrings/kommentarer i `backend/src/` efter gamla paths.
   - Filer att ändra: `backend/README.md`, `backend/Dockerfile`, `backend/src/klartex_se/render.py`, `backend/src/klartex_se/auth.py`

### Fas 2: Infra — en vhost, ingen CORS

1. Skriv om `infra/Caddyfile`
   - `app.klartex.se`-vhosten: reservera hela `/api`-namnrymden med en named matcher — `@api path /api /api/*` (bara `/api/*` missar exakta `/api`) — och `handle @api { reverse_proxy backend:8000 }` (behåll `response_header_timeout 150s`-transporten); flytta in `request_body`-taket (2MB) och `rate_limit`-zonen från API-vhosten med matcher-path uppdaterad till `/api/render`; låt övrig trafik gå till `file_server` + SPA-fallback som idag (`handle`-block runt det statiska).
   - CSP: `connect-src 'self' https://api.klartex.se` → `connect-src 'self'`.
   - Radera hela `api.klartex.se`-vhosten inklusive CORS-preflight-blocket.
   - Filer att ändra: `infra/Caddyfile`
2. Compose-healthcheck
   - `http://localhost:8000/health` → `http://localhost:8000/api/health` i backend-tjänstens healthcheck.
   - Filer att ändra: `infra/docker-compose.yml`
3. `.env.example`
   - `BACKEND_VERSION=0.3.0` → `0.4.0`; kommentaren "POST/DELETE on /page-templates" → `/api/page-templates`.
   - Filer att ändra: `infra/.env.example`
4. Provisionering
   - DNS-instruktionen i `infra/provision.sh` (rad ~86) listar `api.klartex.se A $IP` — raden tas bort.
   - Filer att ändra: `infra/provision.sh`
5. Infra-dokumentation
   - Filtabellen (Caddyfile-raden: två vhosts, inte tre), deploy-verifieringen → `curl -fsS https://app.klartex.se/api/health`, och övriga omnämnanden av `api.klartex.se`.
   - Notera i README:n att DNS-posten för `api.klartex.se` tas bort hos Loopia (om DNS-uppsättningen beskrivs där).
   - Filer att ändra: `infra/README.md`

### Fas 3: CI/deploy — paths i workflowen

1. Smoke-testet i build-jobbet
   - `http://localhost:18000/health` → `/api/health` (båda förekomsterna inkl. wait-loopen), `POST http://localhost:18000/render` → `/api/render`.
   - Filer att ändra: `.github/workflows/deploy.yml`
2. Deploy-jobbets versionsverifiering
   - `curl -fsS http://127.0.0.1:8000/health` → `/api/health`.
   - Kommentaren på rad ~11 om `app.klartex.se` läses igenom och justeras om den beskriver vhost-uppsättningen.
   - Filer att ändra: `.github/workflows/deploy.yml`

### Fas 4: Innehåll — peka om alla adresser

1. `llms.txt`: `https://api.klartex.se` → `https://app.klartex.se/api` (rad ~95, blockschema-referensen) och eventuella andra förekomster.
   - Filer att ändra: `llms.txt`
2. `index.html`: API-avsnittet (rad ~78–79): länk och curl-exempel → `https://app.klartex.se/api/render`.
   - Filer att ändra: `index.html`
3. `PLAN.md`: **Domängräns**-raden i beslutstabellen: `api.klartex.se` utgår; API:et bor på `app.klartex.se/api`. Övriga endpoint-omnämnanden (`/templates/_block/schema`, `/render` i risktabellen) gås igenom: paths som avser den publika HTTP-ytan prefixas, rena begreppsnamn lämnas.
   - Filer att ändra: `PLAN.md`
4. `CLAUDE.md`: kärnprincip punkt 2 listar discovery-endpoints (`/templates`, `/templates/<name>/schema`) — prefixas till `/api/...` så exemplen stämmer med den faktiska ytan.
   - Filer att ändra: `CLAUDE.md`

### Fas 5: Cutover-sekvens och uppföljningar utanför repot

Ordningen spelar roll — `api.klartex.se` dör i steg 2, och rollback efter steg 4 kräver DNS-återställning:

1. Verifiera i `swedev/parla` hur `api_base_url` kombineras med tjänsternas paths, så att `api_base_url = "https://app.klartex.se"` + katalogens endpoint-paths faktiskt ger `https://app.klartex.se/api/...` (syskonens mönster talar för det, men det ska verifieras, inte antas).
2. Merga + deploya detta repo (tag `v0.4.0`). Nya Caddyfilen tar bort `api.klartex.se`-vhosten — gamla adressen slutar svara här, per issuets beslut om ingen deprecation-period.
3. Verifiera publikt: `curl -fsS https://app.klartex.se/api/health` och en `POST /api/render` som ger PDF.
4. `swedev/parla`: `services.toml` → `api_base_url = "https://app.klartex.se"` — egen ändring i parla-repot, direkt efter verifieringen så katalogen inte annonserar ett dött hostname längre än nödvändigt.
5. DNS: droppa `api.klartex.se`-posten hos Loopia — manuellt användarsteg, kan inte göras härifrån.
6. Rollback-notis: före steg 5 räcker det att deploya om v0.3.0 (gamla Caddyfilen följer med repo-checkouten); efter steg 5 måste även DNS-posten återskapas.

## Filöversikt

| Fil | Åtgärd | Syfte |
|-----|--------|-------|
| `backend/src/klartex_se/main.py` | Ändra | Samlande `APIRouter(prefix="/api")`; `/health` → `/api/health`; docs/openapi under `/api`, redoc av |
| `backend/src/klartex_se/render.py` | Ändra | Field-beskrivning "see /page-templates" → `/api/page-templates` |
| `backend/src/klartex_se/auth.py` | Ändra | Docstring-paths → `/api/page-templates`, `/api/render` |
| `backend/tests/test_discovery.py` | Ändra | Paths → `/api/...` |
| `backend/tests/test_page_templates.py` | Ändra | Paths → `/api/...` |
| `backend/tests/test_render.py` | Ändra | Paths → `/api/...`; invariant-test: inga routes utanför `/api` |
| `backend/pyproject.toml` | Ändra | Versionsbump 0.3.0 → 0.4.0 |
| `backend/src/klartex_se/__init__.py` | Ändra | Samma versionsbump (driver `/api/health` + OpenAPI) |
| `backend/README.md` | Ändra | Endpoint-tabell och curl-exempel med `/api`-prefix |
| `backend/Dockerfile` | Ändra | `HEALTHCHECK` → `http://localhost:8000/api/health` |
| `infra/Caddyfile` | Ändra | `@api path /api /api/*`-proxy + body-tak + rate limit in i `app.klartex.se`; CSP → `connect-src 'self'`; `api.klartex.se`-vhosten raderas |
| `infra/docker-compose.yml` | Ändra | Healthcheck → `/api/health` |
| `infra/.env.example` | Ändra | Exempelversion 0.4.0; kommentar → `/api/page-templates` |
| `infra/provision.sh` | Ändra | DNS-instruktionen: `api.klartex.se`-raden bort |
| `infra/README.md` | Ändra | Två vhosts; verifiering `curl -fsS https://app.klartex.se/api/health`; DNS-notis |
| `.github/workflows/deploy.yml` | Ändra | Smoke test + versionsverifiering → `/api/health`, `/api/render` |
| `llms.txt` | Ändra | API-referens → `https://app.klartex.se/api` |
| `index.html` | Ändra | curl-exempel → `https://app.klartex.se/api/render` (obs: PR #45 skriver om samma fil) |
| `PLAN.md` | Ändra | Domängräns-raden + publika endpoint-paths |
| `CLAUDE.md` | Ändra | Discovery-exempel i kärnprincip punkt 2 → `/api/...` |

## Berörda kodområden

- `backend/src/klartex_se/`
- `backend/tests/`
- `infra/`
- `.github/workflows/`
- repo-roten (`llms.txt`, `index.html`, `PLAN.md`)

## Designbeslut

> Icke-triviala val gjorda under planeringen. Feedback välkommen; annars implementeras enligt dessa.

### 1. Prefixet bor i backend, Caddy strippar inte

**Alternativ:** (A) backend monterar allt under `/api` och Caddy proxar `/api/*` orört, vs (B) Caddy `handle_path /api/*` strippar prefixet och backend behåller dagens paths, vs (C) FastAPI `root_path`.
**Beslut:** A.
**Motivering:** Issuet kräver identiska dev- och prod-paths ("Backend mounts all routes under `/api` ... so dev and prod paths are identical and Vite proxies `/api` locally, as styrla does"). Med B skiljer sig lokala paths från prod och Vite-proxyn måste rewrite:a; C är för proxy-strippade uppsättningar och löser inte dev-fallet. Detta är issuetext, inte agentbedömning.

### 2. Samlande `APIRouter(prefix="/api")` i stället för prefix per router

**Alternativ:** ett `prefix="/api"`-argument per `include_router`-anrop + separat flytt av `/health`, vs en parent-router som inkluderar alla tre routers plus health-endpointen.
**Beslut:** Parent-router.
**Motivering:** En plats definierar prefixet; en framtida route kan inte glömma det. Health-endpointen flyttar in i samma router så `/api/health` följer med automatiskt. Agentbedömning — öppen att ifrågasätta, funktionellt likvärdigt med per-router-prefix.

### 3. OpenAPI-ytan flyttar med under `/api`, ReDoc stängs av

**Alternativ:** lämna `/docs` + `/redoc` + `/openapi.json` på FastAPI-default (blir onåbara genom Caddy eftersom bara `/api/*` proxas, och bryter invariant-testet "inga routes utanför `/api`"), vs flytta allt under `/api`.
**Beslut:** `docs_url="/api/docs"`, `openapi_url="/api/openapi.json"`, `redoc_url=None`, `swagger_ui_oauth2_redirect_url="/api/docs/oauth2-redirect"`.
**Motivering:** Ingenting refererar `/docs` idag, men att låta den tyst bli onåbar i prod är en fälla; under `/api` fungerar den i både dev och prod utan extra Caddy-regel. ReDoc är en andra rendering av samma spec — den stängs av i stället för att flyttas. OAuth2-redirecten måste flyttas explicit, annars lämnar FastAPI kvar `/docs/oauth2-redirect` på roten. Agentbedömning — kostnaden är fyra argument i `FastAPI(...)`.

### 4. Versionsbump 0.3.0 → 0.4.0

**Alternativ:** patch (0.3.1) vs minor (0.4.0).
**Beslut:** 0.4.0.
**Motivering:** Varje befintlig API-path bryts — det är inte en patch. Repot är pre-1.0 så minor-bump signalerar brytande ändring enligt gängse 0.x-praxis. Agentbedömning.

### 5. Ingen deprecation-alias för `api.klartex.se`

**Alternativ:** behålla en redirect/alias-vhost en övergångsperiod, vs radera vhost + DNS direkt.
**Beslut:** Radera direkt.
**Motivering:** Uttryckligt användarbeslut i issuet (Provenance: "the immediate removal of `api.klartex.se` (no deprecation alias) are user decisions"). API:et är dagar gammalt och enda kända konsumenten är detta repo.

## Verifieringschecklista

- [ ] `pytest` i `backend/` grönt med alla paths under `/api`, inklusive invariant-testet att ingen route ligger utanför `/api`
- [ ] `GET /api/health` svarar `{"status": "ok", "version": "0.4.0"}` lokalt (`uvicorn`) — och gamla `/health`, `/render`, `/docs`, `/redoc` ger 404
- [ ] `/api/docs` och `/api/openapi.json` svarar
- [ ] `caddy validate` passerar på nya Caddyfilen (deploy-workflowens preflight gör detta, men kör gärna lokalt/i CI först)
- [ ] `infra/Caddyfile` innehåller inte längre `api.klartex.se`, `Access-Control-*` eller CORS-preflight; CSP:n är `connect-src 'self'`
- [ ] Body-taket (2MB) och rate limit-zonen matchar `POST /api/render` i `app.klartex.se`-vhosten; en `POST /api/render` > 2MB ger 413 genom Caddy
- [ ] Genom Caddy: `/api/finns-inte` ger backend-404 (JSON), inte SPA-fallbackens `index.html`; exakta `/api` når backend; en vanlig SPA-route servar `index.html`
- [ ] `backend/Dockerfile`-healthchecken och compose-healthchecken pekar båda på `/api/health`
- [ ] Deploy-workflowens smoke test renderar PDF via `/api/render` och verifierar via `/api/health`
- [ ] `grep -rn "api\.klartex\.se"` i repot ger noll träffar utanför `agent-docs/` (gamla planer/progress får stå kvar som historik)
- [ ] Efter deploy: `curl -fsS https://app.klartex.se/api/health` OK; `curl -X POST https://app.klartex.se/api/render ...` ger PDF
- [ ] Uppföljning (utanför repot, efter verifierad deploy): DNS-posten `api.klartex.se` borttagen hos Loopia
- [ ] Uppföljning (utanför repot): parlas path-komposition verifierad, sedan `swedev/parla` `services.toml` → `api_base_url = "https://app.klartex.se"`
