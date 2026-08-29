# Issue #53: Drop the Swagger docs page: serve /api/openapi.json only, restore the single strict CSP

**Baserad på:** main

## Sammanfattning

PR #51 gav `/api/docs` en egen uppmjukad CSP eftersom Swagger UI laddar script/stylesheet från tredjeparts-CDN — ett undantag i samma origin som webappen och kommande session-cookies (#19). API-publiken är agenter som läser `/api/openapi.json` och `llms.txt`, inte Swagger-HTML. Planen tar bort docs-sidan i backend (`docs_url=None`, OAuth2-redirect bort, `openapi_url` kvar), ersätter Caddys `@docs`/`@notdocs`-dubbelpolicy med en enda strikt CSP i vhost-headerblocket, och låser kontraktet med ett test (`/api/docs` → 404, `/api/openapi.json` → 200). Tre filer, låg risk; bör landa innan `v0.4.0` taggas så undantaget aldrig når produktion.

## Triageringsstatus

| Fält | Värde |
|------|-------|
| **Redo att arbeta** | Ja |
| **Risk** | Låg |
| **Säker för junior** | Ja |

## Plangranskning

**Status:** Granskad
**Granskad:** 2026-08-29
**Feedback:** Codex bekräftade angreppssätt och filval; applicerat: Fas 0-preflight för taggläget (villkorad versionsbump), Caddy-validering via projektets custom-binär (standard-Caddy felar på `rate_limit`), starkare kontraktstest (`/api/render` i `paths`, 404 även för oauth2-redirect) och prod-verifiering via statuskoder/headers i stället för bodys.

## Relaterade filer

- [plan.md](plan.md) — Fullständig implementationsplan
- [progress.md](progress.md) — Implementationsframsteg
- [research.md](research.md) — Forskningsresultat (om finns)

## Relaterade issues

- #50 — Single origin (stängt; PR #51 införde docs-undantaget som nu tas bort)
- #19 — Konton och session-cookies via parla (öppet; motivet till strikt origin)
- #20 — Härdning av /render (öppet; dess Caddy-ändringar ligger redan i trädet)
