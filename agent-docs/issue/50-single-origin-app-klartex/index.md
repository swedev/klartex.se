# Issue #50: Single origin: serve the webapp and the API from app.klartex.se, retire api.klartex.se

**Baserad på:** main

## Sammanfattning

API:et flyttar från `api.klartex.se` till `https://app.klartex.se/api/...` och `api.klartex.se` tas bort helt (vhost + DNS, ingen deprecation-alias). Backend monterar alla routes under `/api` via en samlande router, `app.klartex.se`-vhosten i Caddy proxar `/api/*` till backend och servar frontend-bundlen för allt annat, CORS-blocket raderas och CSP krymper till `connect-src 'self'`. Alla interna referenser följer med: tester, compose-healthcheck, deploy-workflowens smoke test, `llms.txt`, `index.html`, `infra/README.md`, `PLAN.md`. Två uppföljningar ligger utanför repot: DNS-droppen hos Loopia och parla-katalogens `api_base_url`.

## Triageringsstatus

| Fält | Värde |
|------|-------|
| **Redo att arbeta** | Ja |
| **Risk** | Medel |
| **Säker för junior** | Nej |

## Plangranskning

**Status:** Granskad
**Granskad:** 2026-08-28
**Feedback:** Två codex-pass. Tillagt efter feedback: `backend/Dockerfile`-healthchecken, `infra/provision.sh`:s DNS-rad, exakt-`/api`-matchern (`@api path /api /api/*`), OAuth2-redirect under `/api`, route-invariant-test, path-svep i `auth.py`/`render.py`/`.env.example`/`CLAUDE.md`, konflikt med öppna PR #45 (`index.html`), samt cutover-sekvens med rollback-notis (parla före DNS-drop).

## Relaterade filer

- [plan.md](plan.md) — Fullständig implementationsplan

## Relaterade issues

- #14 — MVP fas 1 (frontend) — blockeras av detta: skrivs mot relativa `/api/...` från start
- #19 — Accounts via parla — blockeras av detta: auth föds same-origin
- #21 — Agent-facing site content — dokumenterar en URL-rymd i stället för två
- #23 — Anonym tier på /render — samma
- #46 — App/render-split — bygger vidare på samma `/api`-form senare
