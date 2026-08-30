# Issue #46: Split the backend into a render service and an app service

**Baserad på:** main

## Sammanfattning

Dagens enda backend-container kompilerar anroparstyrd LaTeX i samma miljö som instansens hemligheter, väger 9 GB uppackat och skulle med #19 få Postgres, konton och parla-tokens inbyggda i TeX-containern. Planen delar den i två compose-tjänster: `render` — som är **kärnans artefakt**, byggd och publicerad av `swedev/klartex` vid varje release som `ghcr.io/swedev/klartex-render:<kärnversion>` och konsumerad utan hemligheter, portar, volymer eller nätverk utåt — och `backend` (issuets "app": discovery, tier-policy, page-template-registret och all publik `/api`-trafik, på `python:3.12-slim`, som proxar kompilering till `render` med bundle-innehållet inline). klartex.se bygger aldrig render-imagen och bär **en** kärn-pin plus sin egen appversion. Kärnrepots halva är swedev/klartex#81.

Det publika API-kontraktet får `502 render_unavailable`, och sidmalls-aliasen `formal`/`clean`/`none` försvinner helt — `page_template` blir `str | object` med kärnans slot-form rakt igenom. Tre PR:er: PR 0 återställer deploybarheten på `main`, PR 2a kommer ikapp kärnan på den monolitiska imagen, PR 2b byter till proxy, slim-image och den konsumerade render-imagen.

## Triageringsstatus

| Fält | Värde |
|------|-------|
| **Redo att arbeta** | PR 0: ja. PR 2a och 2b: blockeras av swedev/klartex#81 |
| **Risk** | Medel |
| **Säker för junior** | Nej |

## Plangranskning

**Status:** Granskad
**Granskad:** 2026-08-30
**Feedback:** Första passet (Codex) bekräftade arkitekturen men hittade blockerare i healthcheck, GHCR-synlighet, tidsbudget, felpassthrough och minnesaritmetik — alla inarbetade: explicit timeout-hierarki, exakt passthrough-algoritm, in-process kontraktstest plus tvåcontainer-smoke, korrigerad resursbudget med mätning, och kärnversionen i health. Andra passet rättade semaforordningen, höjde Caddys timeout till 180 s, bytte kontraktstestets transport till Starlettes synkrona `TestClient` och satte resurstaken. Tredje passet (Fable) prövade versionsfrågan mot kärnan och ledde till att render-tjänsten blir kärnans artefakt: en image byggd av `swedev/klartex`, versionerad som kärnan, med **en** pin i klartex.se — plus PR 0 som återställer `main`s deploybarhet, en shim för monolitiska bundlar mot kärnans slot-API, och härdning av render-containern (`no-new-privileges`, `cap_drop: ALL`, `read_only` + tmpfs).

## Relaterade filer

- [plan.md](plan.md) — Fullständig implementationsplan
- [progress.md](progress.md) — Implementationsframsteg

## Relaterade issues

- swedev/klartex#81 — Kärnans halva: `klartex serve` och release-jobbet som publicerar `klartex-render:<version>`. Blockerar PR 2a och 2b
- #47 — `ADMIN_TOKEN`/hemligheter i kompileringsprocessens miljö; den kvarvarande halvan stängs av denna split
- #19 — Konton och parla via Postgres; ska byggas i `backend` efter splitten, inte i TeX-containern
- #23 — Anonym nivå med payload-policy i app-lagret
- #39 — Releasebygget flyttar 9 GB; klartex.se slipper det helt efter splitten
- #20 — Härdning av `/render`; det som återstår där är `openin_any`-sidan (kärnan eller denna split)
- #18 — Assets per anrop; det interna kontraktet har samma form
- #64 — Per-slot-bundlar i registret; följdarbetet efter shimmen i PR 2a
- #14 — Frontend på omergad gren; frontend-paketering ligger utanför denna plan
- swedev/klartex#51 — Sandboxa xelatex i kärnan; komplement, inte förutsättning
