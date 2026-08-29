# Plan: Issue #53 — Drop the Swagger docs page: serve /api/openapi.json only, restore the single strict CSP

## Mål

Ta bort den browsbara Swagger-dokumentationen (`/api/docs`) från backend och därmed CSP-undantaget i Caddy som den krävde. Kvar blir enbart `GET /api/openapi.json` som maskinläsbar API-beskrivning, och `app.klartex.se` får tillbaka en enda strikt same-origin `Content-Security-Policy` för samtliga svar.

## Triagering

> Beslutsunderlag för detta issue.

| Fält | Värde |
|------|-------|
| **Blockeras av** | Inget |
| **Blockerar** | Inget formellt — men bör landa innan `v0.4.0` taggas, så CSP-undantaget aldrig når produktion (se noteringar) |
| **Relaterade issues** | #50 (stängt — single origin, vars PR #51 införde docs-undantaget), #19 (öppet — session-cookies är motivet till att strama åt origin), #20 (öppet — dess edge-härdning ligger redan i trädet) |
| **Omfattning** | 3 filer i `backend/` och `infra/` |
| **Risk** | Låg |
| **Komplexitet** | Låg |
| **Säker för junior** | Ja |
| **Konfliktrisk** | Låg — planen för #20 rör `infra/Caddyfile`, men dess Caddy-ändringar (rate limit-zon, body-tak) landade i PR #25 och ligger i trädet; övriga planer i `agent-docs/issue/` hör till stängda issues (#17, #32, #48, #50) och rör inte dessa rader |

### Triagemässiga noteringar

- CSP-undantaget infördes i PR #51:s reviewrunda som en agentbedömning; detta issue är ett användarbeslut (konversation 2026-08-29) som ersätter den bedömningen. Proveniensen står i issuet.
- Senaste tagg är `v0.3.0`; trädet står på `0.4.0` som ännu inte är taggad. Deploy sker enbart via det taggdrivna workflowet, så undantaget har inte deployats den vägen. Landar detta före `v0.4.0`-taggen skeppas den strikta CSP:n direkt i samma release — releaseordningen "#53 före `v0.4.0`-taggen" är alltså ett explicit önskemål, inte en kodblockerare. Fas 0 verifierar taggläget vid implementationsstart.
- Ingen dokumentation refererar `/api/docs` — verifierat med sökning över `backend/`, `infra/`, `llms.txt`, `index.html`, `PLAN.md` och workflows. `llms.txt` pekar agenter på API:t via endpoints, inte via Swagger-sidan. Inget behöver pekas om.
- Deploy-workflowens smoke test träffar `/api/health` och `POST /api/render` — inte `/api/docs` — så inga workflow-ändringar behövs.

## Angreppssätt

PR #51 gav `/api/docs` en egen uppmjukad CSP i `infra/Caddyfile` eftersom Swagger UI laddar bundle och stylesheet från `cdn.jsdelivr.net`, favicon från `fastapi.tiangolo.com` och bootar från ett inline-script — den strikta same-origin-policyn gjorde sidan blank. Det betyder att två paths på `app.klartex.se` tillåter tredjeparts-CDN-script i samma origin som webappen och, när #19 landar, session-cookies bor i.

klartex API-publik är agenter, och agenter läser `/api/openapi.json` och `llms.txt` — inte Swagger-HTML. I stället för att bära ett CSP-undantag för en sida utan publik tas sidan bort:

1. **Backend** stänger av Swagger UI (`docs_url=None`) och tar bort OAuth2-redirect-routen som bara fanns för dess skull. `openapi_url="/api/openapi.json"` behålls (redoc är redan av). `GET /api/docs` matchar då ingen route och får Starlette/FastAPI:s default-JSON-404, precis som varje annan okänd `/api`-path — korrekt beteende, ingen specialhantering behövs.
2. **Caddy** tappar hela `@docs`/`@notdocs`-dubbelpolicyn och sätter den strikta policyn som en vanlig rad i vhost-omfattande `header`-blocket, sida vid sida med HSTS, `X-Content-Type-Options` och `Referrer-Policy`. Därmed försvinner också den ordningskänsliga matcher-konstruktionen ("matchers must stay mutually exclusive") — en policy, ett ställe.

Det befintliga invariant-testet (`test_every_route_lives_under_api`) fortsätter passera — routes försvinner, inga tillkommer. Ett litet test läggs till som låser det nya kontraktet: `/api/docs` ger 404 och `/api/openapi.json` ger 200.

## Steg

### Fas 0: Preflight — verifiera releaseläget

1. Kontrollera taggläget innan något ändras
   - `git fetch --tags && git tag -l 'v0.4.0'`.
   - Finns `v0.4.0` inte (förväntat läge): ingen versionsbump — ändringen åker med i `0.4.0`-releasen.
   - Finns `v0.4.0`: bumpa till `0.4.1` i `backend/pyproject.toml` och `backend/src/klartex_se/__init__.py` (omfattningen blir då 5 filer i stället för 3).
   - Filer att ändra: inga (ev. `backend/pyproject.toml`, `backend/src/klartex_se/__init__.py`)

### Fas 1: Backend — stäng av Swagger UI

1. Ta bort docs-sidan i FastAPI-konstruktorn
   - Sätt `docs_url=None` (ersätter `docs_url="/api/docs"`).
   - Ta bort argumentet `swagger_ui_oauth2_redirect_url="/api/docs/oauth2-redirect"` helt.
   - Behåll `openapi_url="/api/openapi.json"` och `redoc_url=None`.
   - Filer att ändra: `backend/src/klartex_se/main.py`
2. Testa det nya kontraktet
   - Nytt test i `backend/tests/test_discovery.py`: `GET /api/openapi.json` → 200 och en känd operation finns kvar (t.ex. `"/api/render" in body["paths"]` — inte bara att `paths` existerar, det passerar även för ett tomt schema); `GET /api/docs` → 404 med JSON-body; `GET /api/docs/oauth2-redirect` → 404 (fångar en kvarglömd redirect-route, som är ett eget borttagningskrav).
   - Befintliga tester körs oförändrade; invariant-testet i `test_render.py` verifierar fortsatt att inga routes ligger utanför `/api`.
   - Filer att ändra: `backend/tests/test_discovery.py`

### Fas 2: Caddy — en strikt CSP för hela vhosten

1. Ersätt dubbelpolicyn med en vhost-omfattande rad
   - Ta bort hela blocket med förklaringskommentaren, `@docs`-/`@notdocs`-matcharna och de två `header @…`-raderna i `app.klartex.se`-vhosten.
   - Lägg `Content-Security-Policy "default-src 'self'; connect-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self'"` som en rad i det befintliga `header { … }`-blocket, tillsammans med de övriga säkerhetsheadrarna.
   - Filer att ändra: `infra/Caddyfile`

### Fas 3: Verifiering

1. Kör backend-testerna: `cd backend && pytest`.
2. Validera Caddyfilen med projektets egna Caddy-binär — standard-Caddy felar på tredjepartsdirektivet `rate_limit`. Lokalt: bygg imagen från `infra/caddy/Dockerfile` och kör `caddy validate` i den, motsvarande deploy-workflowets preflight (`deploy.yml`, "caddy validate"-steget). Går det inte att bygga lokalt: notera att valideringen sker i deploy-preflighten före omstart.
3. Efter release/deploy, verifiera statuskoder och headers, inte bara bodys:
   - `curl -s -o /dev/null -w '%{http_code}' https://app.klartex.se/api/docs` → `404`
   - `curl -sI https://app.klartex.se/` och `curl -sI https://app.klartex.se/api/openapi.json` → exakt en `Content-Security-Policy`, utan `cdn.jsdelivr.net` och utan `'unsafe-inline'` i `script-src` (CSP:n ska täcka hela vhosten, därför båda pathsen)
   - `curl -s https://app.klartex.se/api/openapi.json | jq -e '.info.version'` → förväntad backendversion

## Filöversikt

| Fil | Åtgärd | Syfte |
|-----|--------|-------|
| `backend/src/klartex_se/main.py` | Ändra | `docs_url=None`, ta bort `swagger_ui_oauth2_redirect_url` |
| `backend/tests/test_discovery.py` | Ändra | Nytt test: `/api/openapi.json` → 200, `/api/docs` → 404 |
| `infra/Caddyfile` | Ändra | Ta bort `@docs`/`@notdocs`, en strikt CSP i vhost-headerblocket |
| `backend/pyproject.toml` | Ändra (villkorat) | Endast om `v0.4.0` redan taggats: bump till `0.4.1` (Fas 0) |
| `backend/src/klartex_se/__init__.py` | Ändra (villkorat) | Endast om `v0.4.0` redan taggats: bump till `0.4.1` (Fas 0) |

## Berörda kodområden

Lista de primära kataloger/områden som planen berör (för konfliktdetektering):
- `backend/src/klartex_se/`
- `backend/tests/`
- `infra/`

## Designbeslut

> Icke-triviala val gjorda under planeringen. Feedback välkommen; annars implementeras enligt dessa.

### 1. Ingen versionsbump
**Alternativ:** Behålla `0.4.0` vs bumpa till `0.4.1`
**Beslut:** Behålla `0.4.0`
**Motivering:** `v0.4.0` är inte taggad än (senaste tagg `v0.3.0`), så versionen har aldrig släppts — ändringen åker med i samma release och `0.4.0` skeppas direkt med strikt CSP. *Villkor:* Fas 0 kontrollerar taggläget vid implementationsstart; har `v0.4.0` hunnit taggas bumpas versionen i stället till `0.4.1` i `backend/pyproject.toml` och `backend/src/klartex_se/__init__.py`. (Agentens egen bedömning — öppen att ifrågasätta.)

### 2. CSP-värdet är den befintliga `@notdocs`-policyn, oförändrad
**Alternativ:** Kopiera `@notdocs`-raden rakt av vs samtidigt strama åt `style-src 'unsafe-inline'`
**Beslut:** Kopiera rakt av
**Motivering:** Issuet handlar om att ta bort docs-undantaget, inte om att omförhandla den strikta policyn. `style-src 'unsafe-inline'` i basen är ett separat övervägande som i så fall får ett eget issue. (Agentens egen bedömning — öppen att ifrågasätta.)

### 3. Nytt test för 404/200-kontraktet
**Alternativ:** Lita på invariant-testet vs lägga explicit test
**Beslut:** Explicit test i `test_discovery.py`
**Motivering:** Invariant-testet bevisar bara att inga routes ligger utanför `/api` — inte att docs-sidan är borta eller att OpenAPI-JSON:en finns kvar. Två billiga asserts låser exakt det kontrakt issuet fastslår ("agents read `/api/openapi.json`"). (Agentens egen bedömning.)

## Verifieringschecklista

- [ ] `GET /api/docs` och `GET /api/docs/oauth2-redirect` svarar JSON 404 (lokalt via TestClient, i prod via curl med `%{http_code}`)
- [ ] `GET /api/openapi.json` svarar 200 och innehåller API-paths
- [ ] Inga `@docs`/`@notdocs`-matchers kvar i `infra/Caddyfile`; exakt en `Content-Security-Policy` i `app.klartex.se`-vhosten, i det vhost-omfattande `header`-blocket
- [ ] `cdn.jsdelivr.net` och `fastapi.tiangolo.com` förekommer ingenstans i `infra/Caddyfile`
- [ ] `pytest` grönt i `backend/`
- [ ] `caddy validate` passerar (lokalt eller i deploy-workflowet)
- [ ] Ingen kvarvarande referens till `/api/docs` i repo (`grep -rn "api/docs"` exkl. agent-docs)
