# Issue #46: Split the backend into a render service and an app service

**Baserad på:** main

## Sammanfattning

Dagens enda backend-container kompilerar anroparstyrd LaTeX i samma miljö som instansens hemligheter, väger 9 GB uppackat och skulle med #19 få Postgres, konton och parla-tokens inbyggda i TeX-containern. Planen delar den i två compose-tjänster: `render` (tillståndslös inpackning av `klartex.render()` på `klartex-base`, utan hemligheter, portar, volymer eller nätverk utåt) och `backend` (issuets "app": discovery, tier-policy, page-template-registret och all publik `/api`-trafik, på `python:3.12-slim`, som proxar kompilering till `render` med bundle-assets inline). Två images med egna versionsserier (`v*` och `render-v*`) i samma `deploy.yml`. Det publika API-kontraktet förblir oförändrat utom ett tillägg (`502 render_unavailable`). Två PR:er i utrullningsordning: först `render`, sedan `backend`-bytet.

## Triageringsstatus

| Fält | Värde |
|------|-------|
| **Redo att arbeta** | Ja |
| **Risk** | Medel |
| **Säker för junior** | Nej |

## Plangranskning

**Status:** Granskad
**Granskad:** 2026-08-30
**Feedback:** Codex bekräftade arkitekturen och PR-ordningen men hittade två rena blockerare (compose-healthchecken åsidosätter imagens curl-check, som slim-imagen saknar; GHCR-paketet kan vara privat vid första pull) samt luckor i tidsbudget, felpassthrough, integrationstest av `backend → render` och minnesaritmetiken — alla inarbetade: explicit timeout-hierarki, exakt passthrough-algoritm, in-process kontraktstest plus tvåcontainer-smoke vid backend-release, korrigerad resursbudget med mätning före PR 2, pyproject som enda beroendekälla och `klartex`-version i health. Andra passet rättade semaforordningen (plats före bundle-laddning, tak 2), höjde Caddys timeout till 180 s så budgeten summerar, bytte kontraktstestets transport till Starlettes synkrona `TestClient`, satte övergångstak för PR 1 och förklarade varför render-först-fönstret vid kärnbump är ofarligt.

## Relaterade filer

- [plan.md](plan.md) — Fullständig implementationsplan
- [progress.md](progress.md) — Implementationsframsteg
- [research.md](research.md) — Forskningsresultat (om finns)

## Relaterade issues

- #47 — `ADMIN_TOKEN`/hemligheter i kompileringsprocessens miljö; den kvarvarande halvan stängs av denna split
- #19 — Konton och parla via Postgres; ska byggas i `backend` efter splitten, inte i TeX-containern
- #23 — Anonym nivå med payload-policy i app-lagret
- #39 — Releasebygget flyttar 9 GB; produktreleaser slipper det efter splitten
- #20 — Härdning av `/render`; det som återstår där är `openin_any`-sidan (kärnan eller denna split)
- #18 — Assets per anrop; `render`-tjänstens interna kontrakt är samma form
- #14 — Frontend på omergad gren; frontend-paketering ligger utanför denna plan
- swedev/klartex#51 — Sandboxa xelatex i kärnan; komplement, inte förutsättning
