# Framsteg: Issue #53 — Drop the Swagger docs page: serve /api/openapi.json only, restore the single strict CSP

**Påbörjad:** 2026-08-29
**Senast uppdaterad:** 2026-08-29
**Avslutad:** 2026-08-29
**Status:** Klar

## Genomförda steg

- [x] Fas 0, steg 1: Preflight — verifiera taggläget (`v0.4.0` ej taggad, senaste tagg `v0.3.0` → ingen versionsbump)
- [x] Fas 1, steg 1: `docs_url=None` och bort med `swagger_ui_oauth2_redirect_url` i `backend/src/klartex_se/main.py`
- [x] Fas 1, steg 2: Nytt kontraktstest i `backend/tests/test_discovery.py`
- [x] Fas 2, steg 1: En strikt vhost-omfattande CSP i `infra/Caddyfile`, `@docs`/`@notdocs` bort
- [x] Fas 3: Verifiering (pytest grönt, greppar rena; `caddy validate` sker i deploy-preflighten)

## Verifieringschecklista

- [x] `GET /api/docs` och `GET /api/docs/oauth2-redirect` svarar JSON 404 — `test_swagger_ui_is_not_served`
- [x] `GET /api/openapi.json` svarar 200 och innehåller `/api/render` i `paths` — `test_openapi_schema_is_served`
- [x] Inga `@docs`/`@notdocs`-matchers kvar i `infra/Caddyfile`; exakt en `Content-Security-Policy`, i det vhost-omfattande `header`-blocket
- [x] `cdn.jsdelivr.net` och `fastapi.tiangolo.com` förekommer ingenstans i `infra/`
- [x] `pytest` grönt i `backend/` — 36 passed
- [ ] `caddy validate` — körs i deploy-workflowets preflight (`deploy.yml`), se anteckning
- [x] Ingen kvarvarande referens till `/api/docs` i repo utanför kontraktstestet

## Anteckningar

- Fas 0 utfall: `git tag -l 'v0.4.0'` tomt, trädet står på `0.4.0`. Designbeslut 1 gäller i sitt huvudalternativ — ingen versionsbump, ändringen åker med i `0.4.0`-releasen. Omfattningen blev 3 filer som planerat.
- `caddy validate` kunde inte köras lokalt: Docker-daemonen är inte igång och ingen Caddy-binär finns installerad, och standard-Caddy felar ändå på tredjepartsdirektivet `rate_limit`. Valideringen sker i deploy-workflowets preflight (`deploy.yml`, `caddy validate --config … --adapter caddyfile` mot `klartex-se-caddy:local`) före omstart. Ändringen flyttar en `header`-rad in i ett befintligt block och tar bort två matchare — inga nya direktiv införs, och klammerbalansen är kontrollerad.
- Prod-verifieringen i planens Fas 3 steg 3 (curl mot `app.klartex.se`) görs efter release/deploy.
