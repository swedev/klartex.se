# Plan: Issue #19 — Accounts and self-serve API tokens via parla (replaces the Clerk track)

## Mål

Ersätt den delade `API_TOKEN`-miljövariabeln med konton och självbetjänade API-tokens via `swedev-parla`. Tre lager, byggda i ordning: (1) Postgres och användarkonton i backenden (e-post + engångskod, tuttis form), (2) parlas providerhalva monterad i FastAPI-appen med device flow, scopes och rotation, (3) en tokens-/anslutningsvy i frontenden. Därtill måste deployen bli migrationsmedveten (preflight → stop → dump → migrate → start) innan lager 1 släpps till produktion.

## Triagering

> Beslutsunderlag för detta issue.

| Fält | Värde |
|------|-------|
| **Blockeras av** | Inget hårt för fas 1–3. Fas 4 kräver en parla-katalogändring (`api_base_url` → `https://app.klartex.se/api`) och en bump av styrlas parla-pin. Fas 5 — och därmed full stängning av #19, vars tredje lager är tokens-vyn — förutsätter #14 (frontend-scaffold, omergad gren) |
| **Blockerar** | Familjeapparnas anslutningar: styrla listar redan `klartex` i `PARLA_CONSUMES` och kan inte parkoppla förrän providerhalvan finns. Indirekt även #23 (tier-plumbingen delas) |
| **Relaterade issues** | #23 (anonym nivå — samma `render_tier`-yta), #20 (härdning av /render), #14 (frontend), #21 (llms.txt-innehåll — `TOKEN_HOWTO` ändras här), #15/#62 (stängd föregångare: `API_TOKEN`-stopgapen som nu tas bort) |
| **Omfattning** | 30+ filer i `backend/` (moduler, migrations, tester), `infra/`, `.github/workflows/`, `llms.txt`/`index.html`; frontendfiler i `app/` i sista fasen; två små externa ändringar (parla-katalogen, styrlas pin) |
| **Risk** | Hög |
| **Komplexitet** | Hög |
| **Säker för junior** | Nej |
| **Konfliktrisk** | Medel — #14-grenen bär `app/` och infra-ändringar, och #21 rör samma `llms.txt`/`index.html` som `TOKEN_HOWTO`-uppdateringen här. Planen för #20 berör `infra/docker-compose.yml` och deployen, men det repo-lokala arbetet i den är i praktiken redan genomfört (caddy-ratelimit och resurscaps finns i prod) — issuet står öppet för uppströmsdelen |

### Triagemässiga noteringar

- Issuet är uttryckligen skiktat: "three layers that can be built in order". Varje fas nedan är tänkt som en egen PR med `Part of #19`; den sista stängande PR:en får `Closes #19`. Om fas 5 bryts ut till ett eget issue när #14 landat måste #19:s scope justeras i själva issuet innan det stängs — tokens-vyn är ett av dess tre utlovade lager.
- Deploy-ändringarna (fas 1) är ett hårt förkrav för att släppa Postgres till produktion — kommentaren 2026-08-28 i issuet säger uttryckligen att dagens `down`/`up`-restart slutar vara säker i samma ögonblick som `PROVIDER_SQL` finns.
- **Parlas URL-kontrakt:** konsumenter lägger `/auth/device`, `/auth/device/token` och `/.well-known/parla.json` direkt på katalogens `api_base_url`, som idag är `https://app.klartex.se` — men Caddy proxar bara `/api/*` till backenden; allt annat faller igenom till SPA:n. Katalogen behöver alltså peka på `https://app.klartex.se/api` (designbeslut 9), och styrlas pinnade parla-commit (`fd90fb06`, där klartex-posten dessutom pekar på nedlagda `api.klartex.se`) måste bumpas innan fas 4.
- Minnesbudgeten är redan mätt och beslutad i issuet (kommentar 2026-08-31): backend-cap 768m → 256m, vilket frigör rum för Postgres på ~512m inom cax11:ans 3,7 GiB.
- **Rättelse av en premiss i issuet:** kommentaren 2026-08-28 säger att "styrla dumps after writers stop and before migrating". Det stämmer inte — det finns ingen `pg_dump` i styrlas (eller tuttis) deploy; det enda omnämnandet i familjen är aspirationellt (`insector-tutti/agent-docs/tutti-platform-plan.md`). En pre-migrationsdump här är alltså nytt arbete, inte ett mönster att kopiera. Planen inkluderar den ändå (designbeslut 7).
- `swedev-parla` är ett **privat** repo: alla tre ställen som installerar backenden behöver token — pytest-stegen i `ci.yml` och `deploy.yml` samt image-byggena (smoke-bygget och det publicerande bygget) via BuildKit-secret `parla_token` (styrlas mönster, GH-secret `PARLA_REPO_TOKEN`).
- Sidmallsregistret förblir globalt och admin-förvaltat i detta issue: lagringen (`page-templates/<namn>/`) har ingen org-dimension, och `page-templates:write`-scopet grindas av admin vid godkännandet. Per-org-ägande av bundles är ett eget senare beslut.

## Angreppssätt

Backenden är idag tillståndslös FastAPI utan databas; auth är en enda delad `API_TOKEN` i `backend/src/klartex_se/auth.py` med två dependencies (`require_api_token`, `render_tier`). Parlas providerhalva förutsätter Postgres (`parla.schema.PROVIDER_SQL`, två tabeller `parla_machine`/`parla_grant`, där appen själv lägger FK:n `parla_machine.org_id → org(id)`) och en inloggad användare med org-id som kan godkänna en parkoppling i webbläsaren.

Byggstenarna finns färdiga i familjen:

- **parla** (`../parla`): `provider_router(provider, get_conn, current_org_id, prefix=...)` monterar hela ytan — `/.well-known/parla.json`, `/auth/device`, `/auth/device/token`, `/auth/device/rotate` (publika) samt `/data/connections/*` och `/action/connections/*` (kräver inloggad org). `machine_auth(provider, get_conn)` ger en `Principal` från bearer-headern och `require_scope(...)` gör scope-kontrollen — men observera `Principal.has_scope`: **användare passerar alla scope-kontroller implicit**, så admin-grind och maskin-scope måste vara separata dependencies. `get_conn` ska ge en psycopg3-connection med `row_factory=dict_row`. Klartex finns redan i `parla/catalog/services.toml`.
- **tutti** (`../insector-tutti`): inloggningsformen (e-post → sexsiffrig kod, HMAC:ad med `LOGIN_CODE_SECRET` som aldrig ligger i databasen, `pg_advisory_xact_lock` runt cooldown, enumeration-säkra generiska svar, sessionscookie `httponly/lax/secure`), bearer-först-`current_user`, samt tokens-vyn i frontenden (`frontend/src/pages/tokens.tsx`, `components/token-reveal.tsx`, maskad visning via `suffix`-kolumn). Tuttis `parla_transaction()`-brygga visar hur en SQLAlchemy-app ger parla den psycopg-connection den vill ha.
- **styrla** (`../styrla`): deploy-sekvensen — `compose pull` → `run --rm app alembic current` (preflight mot nya imagen medan gamla appen servar; fångar rollback över en migration innan produktionen tas ner) → `stop` → `run --rm app alembic upgrade head` → `up -d`, forward-only-policy — samt migrationskonventionen: frusen kopia av parlas SQL i den egna migrationen (`migrations/versions/0006_parla.py`) med FK:n tillagd där.

Ordningen nedan lägger deploy- och infragrunden först (fas 1), eftersom inget av de senare lagren kan släppas utan den. Alla persistenta koder/sessioner/tokens lagras hashade; parla-tokens lagras som bar sha256 hos providern och levereras i klartext exakt en gång.

## Steg

### Fas 1: Postgres, migrationsgrund och migrationsmedveten deploy

1. Databasmodul och alembic-miljö
   - Nya beroenden: `sqlalchemy>=2.0`, `alembic>=1.13`, `psycopg[binary]>=3.2`
   - `db.py` med engine/sessionsfabrik från `DATABASE_URL`; alembic-miljö under `backend/migrations/` (styrlas layout), körbar som `alembic upgrade head` i containern; alembic-filerna in i imagen
   - Backend ska starta och svara på `/api/health` även utan nåbar databas — health-endpointen är liveness, inte readiness
   - Filer att ändra: `backend/pyproject.toml`, `backend/Dockerfile`; nya: `backend/src/klartex_se/db.py`, `backend/alembic.ini`, `backend/migrations/env.py`
2. Migrationstester i CI mot riktig Postgres
   - `ci.yml`: Postgres som service-container för pytest (PROVIDER_SQL och `pg_advisory_xact_lock` är Postgres-only — testa mot rätt dialekt, inte SQLite)
   - Migrationstester som egen svit (styrlas mönster `test_migration_*`): färsk `upgrade head`, `downgrade`, och att modellerna stämmer mot head
   - Filer att ändra: `.github/workflows/ci.yml`; nya: `backend/tests/test_migrations.py`
3. Postgres i produktionsstacken
   - `postgres:18-alpine`, named volume `pgdata:/var/lib/postgresql`, `pg_isready`-healthcheck (5s/5s/10), ingen publicerad port (familjekonventionen från styrla/tutti)
   - Resursbudget enligt issuets mätning: `mem_limit`/`memswap_limit` 512m på postgres, backend 768m → 256m; uppdatera budgetkommentaren överst i filen
   - `POSTGRES_PASSWORD` via `.env` (`:?`-krav), `backend` får `DATABASE_URL` och `depends_on: postgres: condition: service_healthy`
   - Filer att ändra: `infra/docker-compose.yml`, `infra/.env.example`
4. Deploy-sekvensen: preflight → stop → dump → migrate → start
   - I `deploy.yml`s remote-block, efter `docker compose pull` men före omstarten: `docker compose run --rm backend alembic current` mot **nya** imagen medan gamla stacken servar — en image som inte kan lösa databasens aktuella revision (rollback över en migration) ska fela här, innan produktionen tas ner
   - Därefter: `docker compose stop backend` → `pg_dump` (via `docker compose exec -T postgres pg_dump …`) till `/home/klartex/db-backups/` — **utanför** rsync-målet `~/klartex/` så `--delete` aldrig rör dumparna — med `umask 077`, roterande de 5 senaste, och en trivial verifiering (icke-tom fil, gzip-integritet) → `docker compose run --rm backend alembic upgrade head` → `systemctl restart klartex-stack.service`
   - Restore-trappens semantik ändras: efter en **lyckad** migration får feltrappen inte automatiskt starta den gamla imagen igen — det vore själv en osupportad rollback över migrationsgränsen. Sätt en `migrated=1`-flagga i skriptet; fel efter den punkten stannar med stacken nere, pekar på dumpen och det dokumenterade restore-kommandot (`gunzip -c <dump> | docker compose exec -T postgres psql …`) i stället för att köra `restore()`
   - Dokumentera forward-only-policyn i workflow-kommentaren och `infra/README.md`: rollback via `workflow_dispatch` stöds bara till versioner på samma migrations-head; restore-kommandot och dumprutinen dokumenteras på samma ställe
   - Filer att ändra: `.github/workflows/deploy.yml`, `infra/README.md`
5. Smoke-testet i release-bygget får databas
   - En postgres-container på smoke-nätet + `alembic upgrade head` innan backend startas
   - Filer att ändra: `.github/workflows/deploy.yml`

### Fas 2: Konton — e-post + engångskod, sessioner, org

1. Modeller och migration `0001_accounts`, med schemat utskrivet
   - `org`: `id uuid PK`, `name`, `created_at`
   - `users`: `id uuid PK`, `email` (normaliserad till gemener före lagring; unikt index på `lower(email)` så invarianten hålls i Postgres), `org_id FK org.id ON DELETE CASCADE`, `created_at`; admin-status härleds i kod ur `ADMIN_EMAILS`, ingen kolumn
   - `login_tokens`: `id`, `email` (indexerad), `code_hash` (HMAC-sha256), `code_attempts int default 0`, `created_at` (cooldownen räknar på den), `expires_at`, `used bool`
   - `sessions`: `id`, `user_id FK users.id ON DELETE CASCADE`, `token_hash` sha256 unik, `created_at`, `expires_at`
   - Filer: nya `backend/src/klartex_se/models.py`, `backend/migrations/versions/0001_accounts.py`
2. Auth-endpoints, i tuttis form men självbetjänade (ingen `ALLOWED_EMAILS`-allowlist)
   - `POST /api/auth/request-code` (generiskt svar oavsett utfall, cooldown 60 s under `pg_advisory_xact_lock`), `POST /api/auth/code` (en guardad `UPDATE … WHERE used=FALSE AND expires_at>=now() AND code_attempts<5`, identiskt 400-svar för fel/förbrukad/utgången kod; skapar user + en-persons-org vid första inloggning), `POST /api/auth/logout`, `GET /api/me`
   - Sessionscookie: `httponly`, `samesite=lax`, `secure` när basen är https, `Cache-Control: no-store` på auth-svaren
   - Origin-kontroll på **alla** cookie-autentiserade skrivningar (logout, och i fas 3: approve/deny/disable) plus de oautentiserade auth-endpointsen — frånvarande Origin passerar, så curl/agenter fungerar
   - Per-IP-strypning av `request-code` utöver e-post-cooldownen — annars kan en oautentiserad anropare skicka mejl till obegränsat många adresser. Läggs i Caddy som en `rate_limit`-zon på `POST /api/auth/request-code` (mekanismen finns redan för `/api/render`)
   - Städning av utgångna rader: opportunistisk `DELETE` av utgångna `login_tokens`/`sessions` i samband med `request-code`/inloggning (plus parlas `sweep_expired` i fas 3) — den publika endpointen får inte växa tabellerna obegränsat
   - Kodutskick via SMTP (`SMTP_*`-env); `email-validator` (Pydantics `EmailStr`) som beroende
   - **`LOGIN_CODE_SECRET` är obligatorisk**: appen vägrar starta utan (ingen per-process-fallback — den bryter utestående koder vid omstart och mellan workers); testerna sätter den explicit
   - Filer: ny `backend/src/klartex_se/accounts.py`; ändra `backend/src/klartex_se/main.py`, `infra/Caddyfile`; nya tester `backend/tests/test_accounts.py`
3. Konfiguration
   - Nya env-nycklar dokumenterade i `.env.example`: `DATABASE_URL`, `LOGIN_CODE_SECRET`, `ADMIN_EMAILS`, `SMTP_*`, `BASE_URL`
   - Filer: `infra/.env.example`, `infra/docker-compose.yml` (environment-blocket), `backend/README.md`

### Fas 3: Parlas providerhalva — device flow, scopes, `API_TOKEN` bort

0. Förkrav uppströms: rätta parlas URL-kontrakt (designbeslut 9)
   - PR mot `swedev/parla`: `api_base_url = "https://app.klartex.se/api"` i `catalog/services.toml`; klartex pinnar den resulterande committen. Konsumenter lägger protokollvägarna direkt på basen, så manifest och device-endpoints hamnar då under `/api/*` som Caddy redan proxar
1. Beroende och bygge
   - `swedev-parla[fastapi] @ git+https://github.com/swedev/parla@<committen från steg 0>` i `pyproject.toml`; `PARLA_REPO_TOKEN` på **alla tre** installationsvägarna: pytest-stegen i `ci.yml` och `deploy.yml` samt BuildKit-secret `parla_token` i bägge image-byggena (smoke + publish)
   - Filer: `backend/pyproject.toml`, `backend/Dockerfile`, `.github/workflows/ci.yml`, `.github/workflows/deploy.yml`
2. Migration `0002_parla`
   - Frusen ordagrann kopia av `parla.schema.PROVIDER_SQL` vid den pinnade committen (familjekonventionen: migrationshistoriken tillhör klartex — ett paketbump får inte tyst ändra vad en färsk databas får) + `ALTER TABLE parla_machine ADD CONSTRAINT … FOREIGN KEY (org_id) REFERENCES org(id) ON DELETE CASCADE`, med riktig `downgrade()`
   - Filer: ny `backend/migrations/versions/0002_parla.py`
3. Provider-konfiguration och montering
   - `Provider(token_prefix='kx_', registry=catalog.all(), scopes={'render:write': …, 'page-templates:write': …}, service_name='klartex', base_url=BASE_URL, verification_path='/pair')`
   - `parla_transaction()`/`get_parla_db()` — psycopg-bryggan med `dict_row`, commit/rollback ägd av appen (tuttis `connections.py`-form); `current_parla_org_id` från sessionsanvändarens org
   - Montera routern **platt** med `prefix='/api'` (FastAPI ≥0.141 döljer nästlade routrar — dokumenterad fallgrop i tutti) och lägg auth **per skyddad route-grupp, inte på hela routern**: `/.well-known/parla.json` och `/auth/device*` måste vara publika (tutti privatiserade av misstag manifestet)
   - Filer: ny `backend/src/klartex_se/connections.py`; ändra `backend/src/klartex_se/main.py`
4. Auktorisationsmodellen: scopes på riktigt, inte bara tier
   - `render_tier` ersätts av en access-modell som bär maskin-principalens scopes: ingen Authorization-header → anonym; giltig `kx_`-bearer → principal; ogiltig token förblir 401, aldrig tyst nedgradering. `latex`-blocket kräver **uttryckligen scopet `render:write`** — en token med bara `page-templates:write` (eller tomma scopes) låser inte upp det
   - Page-template-skrivningar: **två separata dependencies** — maskin med scopet `page-templates:write` (via `require_scope` på maskin-principal) *eller* inloggad admin-session (`ADMIN_EMAILS`-kontroll). De blandas aldrig i en kombinerad principal, eftersom parlas `Principal.has_scope` låter användare passera alla scope-kontroller implicit
   - Godkännande-guarden ligger på de **inskickade beviljade scopen**, inte de begärda: en approve vars scopes innehåller `page-templates:write` kräver att godkännaren är admin, innan `approve_grant` anropas
   - `API_TOKEN`-sökvägen tas bort helt: koden, `503 token_not_configured`, compose-miljön, `.env.example`, testerna
   - `TOKEN_HOWTO` uppdateras till självbetjäningsflödet (påverkar `llms.txt` och `index.html`, som upprepar den ordagrant, samt `backend/README.md`)
   - Tester: scope-substitution (fel scope → 403 `insufficient scope`), token utan scopes, icke-admin-session mot page-templates, icke-admin-approve av `page-templates:write`, roterad-förbi-grace/inaktiverad token → 401
   - Filer: `backend/src/klartex_se/auth.py`, `backend/src/klartex_se/page_template_router.py`, `backend/src/klartex_se/render.py`, `backend/tests/test_render.py`, `backend/tests/test_page_templates.py`, nya `backend/tests/test_connections.py`, `infra/docker-compose.yml`, `infra/.env.example`, `llms.txt`, `index.html`, `backend/README.md`
5. Minimala serverrenderade `/pair`- **och `/login`**-sidor i backenden (tills #14 landat)
   - `/pair`: hämtar `GET /api/data/connections/pairing?code=`, visar tjänst + begärda scopes, knappar approve/deny; kräver inloggad session
   - `/login`: e-post → kod-formulär ovanpå fas 2-endpointsen — utan den är `/pair`s "skicka till inloggning" en återvändsgränd, eftersom ingen frontend finns än. En validerad **lokal** retur-URL (`/pair?code=…`, aldrig extern) följer med genom inloggningen
   - Bägge i grafiska profilens stil (jfr landningssidan: inline-CSS, ingen build); Caddy måste proxa `/pair` och `/login` till backenden — idag faller allt utanför `/api` igenom till SPA:n
   - Referenser i form: `styrla/frontend/src/pages/Pair.tsx`, `tutti/frontend/src/pages/device.tsx`
   - Filer: ny `backend/src/klartex_se/pair.py` (bägge routes + templates), ändra `backend/src/klartex_se/main.py`, `infra/Caddyfile`
6. Smoke-test-uppdatering: device flow-rundan mot den nybyggda imagen
   - Seedning utan SMTP och utan test-endpoints: ett engångskommando i backend-containern (`docker compose run --rm backend python -m klartex_se.smoke_seed` eller motsvarande inline-`python -c`) skriver user + org + sessionsrad direkt i databasen; smoke-skriptet använder den sessionen för approve
   - Rundan: starta grant → godkänn via API med seedad session → polla ut token → rendera `latex`-block med den → verifiera att andra pollen inte får token igen

### Fas 4: Verifiering i familjen

0. Förkrav: styrlas parla-pin bumpad till en commit där klartex-posten pekar på `https://app.klartex.se/api` (dagens pin `fd90fb06` bär nedlagda `api.klartex.se`), och styrla släppt med den
1. Parkoppla styrla → klartex på riktigt: styrla listar redan `klartex` i `PARLA_CONSUMES`, så en parkoppling ska gå att genomföra från styrlas inställningssida mot `app.klartex.se`
2. Uppdatera `PLAN.md`-tabellraden för auth om lydelsen behöver justeras, samt `infra/README.md`:s "Saker som inte finns här"-lista (databasen finns nu; backups-raden ersätts av dumprutinen)

### Fas 5: Tokens-/anslutningsvy i frontenden (efter #14)

1. Vyer i `app/` när frontend-scaffolden finns på `main`
   - Anslutningsvy: lista parla-maskiner (`list_machines` — namn, tjänst, scopes, status, `last_used_at`), inaktivera (`disable`); `/pair` och `/login` flyttar in i appen och ersätter de serverrenderade sidorna
   - Ev. personliga tokens i tuttis form (`tokens.tsx` + `token-reveal.tsx`, maskad `kx_••••abcd` via `suffix`) — se designbeslut 6
2. Bryts fasen ut till ett eget issue när #14 landat måste #19:s scope-beskrivning justeras innan #19 stängs — fas 1–4 uppfyller kärnlöftet (självbetjänade tokens utan handhållning) för maskin-anropare, men issuet beskriver vyn som sitt tredje lager

## Filöversikt

| Fil | Åtgärd | Syfte |
|-----|--------|-------|
| `infra/docker-compose.yml` | Ändra | Postgres-tjänst; backend-cap 768m → 256m; `DATABASE_URL` m.fl. env; `API_TOKEN` bort |
| `infra/.env.example` | Ändra | `POSTGRES_PASSWORD`, `DATABASE_URL`, `LOGIN_CODE_SECRET`, `ADMIN_EMAILS`, `SMTP_*`; `API_TOKEN` bort |
| `infra/README.md` | Ändra | Databas-, dump/restore- och forward-only-dokumentation; minnesbudgeten |
| `infra/Caddyfile` | Ändra | Proxy för `/pair` och `/login` till backenden; rate_limit-zon på `/api/auth/request-code` |
| `.github/workflows/deploy.yml` | Ändra | Preflight `alembic current` → stop → `pg_dump` → migrate → start; migrated-flagga i feltrappen; smoke-test med postgres + device flow; `PARLA_REPO_TOKEN` |
| `.github/workflows/ci.yml` | Ändra | Postgres-service för pytest; `PARLA_REPO_TOKEN` för pip-install |
| `backend/pyproject.toml` | Ändra | sqlalchemy, alembic, psycopg, email-validator, swedev-parla[fastapi]; versionsbump per fas |
| `backend/Dockerfile` | Ändra | BuildKit-secret för privata parla-repot; alembic-filer in i imagen |
| `backend/alembic.ini`, `backend/migrations/` | Skapa | Migrationsmiljö + `0001_accounts`, `0002_parla` |
| `backend/src/klartex_se/db.py` | Skapa | Engine/sessionsfabrik från `DATABASE_URL` |
| `backend/src/klartex_se/models.py` | Skapa | `org`, `users`, `login_tokens`, `sessions` |
| `backend/src/klartex_se/accounts.py` | Skapa | Kodinloggning, sessioner, `/api/me`, `current_user`, radstädning |
| `backend/src/klartex_se/connections.py` | Skapa | `Provider`-konfig, psycopg-bryggan, montering av `provider_router`, approve-guarden |
| `backend/src/klartex_se/pair.py` | Skapa | Serverrenderade `/pair`- och `/login`-sidor |
| `backend/src/klartex_se/auth.py` | Ändra | Access-modell med scopes via parla-principal; `API_TOKEN`-sökvägen bort; nytt `TOKEN_HOWTO` |
| `backend/src/klartex_se/page_template_router.py` | Ändra | Maskin-scope `page-templates:write` *eller* admin-session |
| `backend/src/klartex_se/render.py` | Ändra | `latex`-blocket kräver scopet `render:write` |
| `backend/src/klartex_se/main.py` | Ändra | Nya routrar monteras |
| `backend/tests/` | Ändra/Skapa | Konto-, migrations-, scope- och tier-tester; `API_TOKEN`-tester ersätts |
| `backend/README.md` | Ändra | Autentiseringsavsnittet skrivs om |
| `llms.txt`, `index.html` | Ändra | Token-instruktionen (idag "email kontakt@klartex.se") ersätts med självbetjäningsflödet |
| `app/…` (fas 5) | Skapa | Tokens-/anslutningsvy + `/pair`/`/login` i appen, efter #14 |
| *(externt)* `parla/catalog/services.toml` | Ändra | `api_base_url` → `https://app.klartex.se/api` (egen PR mot swedev/parla) |
| *(externt)* `styrla/requirements.txt` | Ändra | Parla-pin bumpad förbi katalogrättelsen (egen PR mot styrla, före fas 4) |

## Berörda kodområden

Lista de primära kataloger/områden som planen berör (för konfliktdetektering):
- `backend/` (hela: nya moduler, migrations, tester, Dockerfile, pyproject)
- `infra/` (docker-compose.yml, .env.example, README.md, Caddyfile)
- `.github/workflows/` (ci.yml, deploy.yml)
- rot (`llms.txt`, `index.html`, `PLAN.md`)
- `app/` (endast fas 5)

## Designbeslut

> Icke-triviala val gjorda under planeringen. Feedback välkommen; annars implementeras enligt dessa.

### 1. Alembic från dag ett, inte tuttis `create_all` + mikromigrationer
**Alternativ:** tuttis `Base.metadata.create_all` + handskrivna `ADD COLUMN IF NOT EXISTS` vs styrlas alembic
**Beslut:** alembic
**Motivering:** Deploy-kravet i issuet (användarbeslut, kommentar 2026-08-28) är styrlas sekvens, och dess preflight *är* `alembic current` — utan alembic finns inget revisionsbegrepp att preflighta mot. Tutti kommenterar själv sin lösning med "switch to alembic once the model set stabilizes".

### 2. Endast sexsiffrig kod — ingen magisk länk
**Alternativ:** tuttis fulla form (länk + kod på samma rad) vs enbart kod
**Beslut:** enbart kod
**Motivering:** Issuet (användarbeslut) pekar på tuttis form som "closest to the right size" och beskriver den som "email → six-digit code". Länkhalvan drar med sig scanner-problematiken (`GET /verify` som inte får förbruka) utan att tillföra något för klartex användarfall. *Agentens bedömning i avgränsningen — öppen att ifrågasätta.*

### 3. Org-modell: en en-persons-org per användare vid första inloggning
**Alternativ:** synthetic fast org (tuttis väg — men då finns inget FK-mål) vs org-tabell med en org per användare vs full org-hantering med medlemskap
**Beslut:** org-tabell med `uuid` PK, en org skapas per användare vid första inloggning
**Motivering:** `parla_machine.org_id` behöver ett riktigt FK-mål (`ON DELETE CASCADE`), och PLAN.md:s fas 5 nämner organisationer som konceptet. Fullt medlemskap (flera användare per org, inbjudningar) skjuts framåt — schemat hindrar det inte. *Agentens bedömning — öppen att ifrågasätta.*

### 4. Vem godkänner en parkoppling
**Alternativ:** endast `ADMIN_EMAILS` godkänner allt vs varje inloggad användare godkänner för sin egen org, admin-krav enbart för `page-templates:write`
**Beslut:** varje inloggad användare godkänner parkopplingar mot sin egen org; en approve vars **beviljade** scopes innehåller `page-templates:write` kräver att godkännaren finns i `ADMIN_EMAILS` (guarden ligger på det inskickade godkännandet, före `approve_grant` — inte på vad som ursprungligen begärdes)
**Motivering:** Issue-bodyn säger att vem som helst ska kunna skaffa token själv (självbetjäning); kommentaren 2026-08-30 säger att serverkonfigurationen ska vara admin-adresserna som "can approve machine pairings … and write page templates". Planen läser kommentaren som att admin-listan är den *enda kvarvarande server-side-konfigurationen*, inte att bara admins får para — annars vore flödet inte självbetjänat. *Tolkningen är agentens bedömning av två användarkällor i lätt spänning — måste bekräftas före implementation av fas 3.*

### 5. Minimala serverrenderade `/pair`- och `/login`-sidor i backenden tills #14 landat
**Alternativ:** vänta med hela device flow-ytan på #14 vs enkla HTML-sidor ur FastAPI
**Beslut:** enkla serverrenderade sidor, bägge två
**Motivering:** Utan godkännandesida är device flow obrukbar, och utan inloggningssida är godkännandesidan det — #14:s källa ligger på en omergad gren utan tidsplan. Sidor i grafiska profilens stil (jfr landningssidan: inline-CSS, ingen build) håller lager 2 leveransbart fristående. Ersätts av appvyerna i fas 5. *Agentens bedömning — öppen att ifrågasätta.*

### 6. Personliga tokens (tuttis `api_tokens`-form) skjuts till fas 5 och beslutas där
**Alternativ:** bara parla-maskiner vs även en "skapa token"-knapp med egen tabell (`suffix`-maskning `kx_••••abcd`)
**Beslut:** fas 1–4 bygger enbart parla-vägen; personliga tokens tas ställning till i fas 5
**Motivering:** Issuets maskningsexempel (`kx_••••abcd`) kommer från tuttis personliga tokens, som är en egen tabell vid sidan av parla — parla kan inte minta en maskin utan device flow. För maskin-anropare räcker parla-vägen; en klicka-fram-token är främst en människo-bekvämlighet som hör hemma i token-vyn. *Agentens bedömning — öppen att ifrågasätta.*

### 7. Pre-migrationsdump trots att styrla saknar en
**Alternativ:** kopiera styrla rakt av (ingen dump) vs `pg_dump` på servern mellan stop och migrate
**Beslut:** `pg_dump` till roterande fil under `/home/klartex/db-backups/` (utanför rsync-målet), efter stop och före migrate — då är dumpen en konsistent återställningspunkt för exakt den operation som kan förstöra datan
**Motivering:** Issuets kommentar (användarbeslut till innehållet, även om dess styrla-premiss visade sig felaktig) begär precis den återställningspunkten. Kostnaden är några rader i deployen; databasen är liten. Riktiga off-site-backups (Hetzner "automatic backups" eller nightly dump) är ett eget beslut och lämnas utanför.

### 8. `token_prefix='kx_'`
**Motivering:** Issuet använder `kx_••••abcd` som exempel (användarkälla); kort, kollisionsfritt mot `stm_`/`tutti_`.

### 9. Parla-katalogen rättas till `https://app.klartex.se/api` i stället för att klartex proxar rotvägar
**Alternativ:** ändra katalogens `api_base_url` (+ pin-bump hos klartex och styrla) vs proxa/skriva om `/.well-known/parla.json` och `/auth/device*` på rotten i Caddy
**Beslut:** ändra katalogen
**Motivering:** Konsumenter lägger protokollvägarna direkt på `api_base_url`; med `/api` i basen hamnar allt under prefixet Caddy redan proxar, och backendens montering förblir en rad. Rot-proxyn skulle sprida parla-vägar över två lager och behöva underhållas i takt med protokollet. Kräver att styrlas pin bumpas före fas 4 — dagens pin bär dessutom nedlagda `api.klartex.se`, så bumpen behövs oavsett. *Agentens bedömning — öppen att ifrågasätta.*

## Verifieringschecklista

- [ ] Device flow end-to-end: `POST /api/auth/device` → godkännande på `/pair` som inloggad → poll levererar token exakt en gång → grant-raden borta
- [ ] Browser-flödet utloggad → `/login` (begär kod → ange kod) → tillbaka till `/pair?code=…` → godkänn — utan frontend-appen
- [ ] Scope-modellen: `latex`-block kräver `render:write` (token med bara `page-templates:write` eller tomma scopes → 403 `insufficient scope`); page-template-skrivning kräver maskin-scope `page-templates:write` *eller* admin-session; icke-admin kan inte godkänna en grant med `page-templates:write`
- [ ] Anonymt beteende oförändrat: rendering utan header fungerar, `latex`-block svarar 403 med begriplig `detail`
- [ ] Ogiltig/roterad-förbi-grace/inaktiverad token → 401, aldrig tyst nedgradering till anonym
- [ ] Ingen `API_TOKEN`-referens kvar i kod, compose, `.env.example`, README, `llms.txt`, `index.html`
- [ ] Inloggningen är enumeration-säker: identiska svar för okänd adress, cooldown och lyckad begäran; kod-verifiering svarar identiskt för fel/förbrukad/utgången/max-försök; `request-code` är per-IP-strypt i Caddy
- [ ] `LOGIN_CODE_SECRET`-HMAC: koderna värdelösa vid tabelläcka; appen vägrar starta utan secreten; sessioner och tokens lagras enbart hashade; utgångna `login_tokens`/`sessions` städas
- [ ] Migrationstester gröna mot riktig Postgres: färsk `upgrade head`, `downgrade`, modeller mot head
- [ ] Deploy-rundan: tagg → preflight (`alembic current` mot ny image medan gamla servar) → stop → dump (icke-tom, läsbar, roterad, `0600`) → migrate → start → hälsokontroller gröna
- [ ] Rollback över en migrationsgräns felar i preflighten, **innan** stacken stoppas; fel **efter** lyckad migration startar inte gamla imagen automatiskt utan pekar på dumpen och restore-kommandot
- [ ] Restore-kommandot testat en gång på riktigt (dump → återställ → appen svarar)
- [ ] `docker stats` efter release: backend under 256m-capen, postgres under 512m
- [ ] Manifestet `https://app.klartex.se/api/.well-known/parla.json` och `/api/auth/device*` nåbara utan inloggning; styrla (med bumpad pin) kan parkoppla mot klartex
- [ ] Backend svarar på `/api/health` även när databasen är nere
