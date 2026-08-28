# Framsteg: Issue #50 — Single origin: serve the webapp and the API from app.klartex.se, retire api.klartex.se

**Påbörjad:** 2026-08-28
**Senast uppdaterad:** 2026-08-28
**Färdigställd:** 2026-08-28
**Status:** Klar

## Genomförda steg

- [x] Fas 1, steg 1: Samlande `APIRouter(prefix="/api")` i `main.py`, `/health` under prefixet, docs/openapi under `/api`
- [x] Fas 1, steg 2: Tester till `/api`-paths + invariant-test att ingen route ligger utanför `/api`
- [x] Fas 1, steg 3: Versionsbump 0.3.0 → 0.4.0
- [x] Fas 1, steg 4: Backend-dokumentation och path-referenser i kod (`README.md`, `Dockerfile`, `render.py`, `auth.py`)
- [x] Fas 2, steg 1: `infra/Caddyfile` — en vhost, `@api`-matcher, CSP `connect-src 'self'`, `api.klartex.se` raderad
- [x] Fas 2, steg 2: Compose-healthcheck → `/api/health`
- [x] Fas 2, steg 3: `infra/.env.example` — version 0.4.0, path-kommentar
- [x] Fas 2, steg 4: `infra/provision.sh` — DNS-raden för `api.klartex.se` bort
- [x] Fas 2, steg 5: `infra/README.md` — två vhosts, verifierings-URL, A-postlistan
- [x] Fas 3, steg 1: Smoke test i `deploy.yml` → `/api/health`, `/api/render`
- [x] Fas 3, steg 2: Deploy-jobbets versionsverifiering → `/api/health`
- [x] Fas 4, steg 1: `llms.txt` → `https://app.klartex.se/api`
- [x] Fas 4, steg 2: `index.html` → `https://app.klartex.se/api/render`
- [x] Fas 4, steg 3: `PLAN.md` — domängräns och publika endpoint-paths
- [x] Fas 4, steg 4: `CLAUDE.md` — discovery-exempel med `/api`-prefix

## Status

Alla faser i planen är genomförda. Fas 5 är en cutover-sekvens som utförs vid deploy, inte i PR:en.

## Anteckningar

Fas 5 (cutover) utförs inte här — den är en deploy- och uppföljningssekvens utanför PR:en (DNS hos Loopia, `swedev/parla` `services.toml`).

Avsteg från planen: `infra/README.md` fick ingen notis om att DNS-posten för `api.klartex.se` tas bort. README:n beskriver nuläget i driftsetupen och listar nu bara de A-poster som gäller; cutover-steget hör hemma i PR-bodyn och issuet.

Verifierat lokalt med Caddy 2.11.4 (`rate_limit`-blocket borttaget — tredjepartsmodulen finns bara i serverimagen) mot uvicorn: `/api/health` 200, exakta `/api` når backend med JSON-404 i stället för SPA-fallback, `/apifoo` faller igenom till SPA:n, `POST /api/render` > 2 MB ger 413 och en giltig render ger `%PDF`. Backendens gamla paths (`/health`, `/render`, `/docs`, `/redoc`) ger 404.

`app/dist/` är otrackad lokal build-output från #14-grenen och innehåller fortfarande gamla adressen; den byggs om från #14:s källa.
