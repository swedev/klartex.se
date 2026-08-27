# Issue #17: Kom ikapp klartex 0.14.0: bumpa pinnen, hantera breaking changes, uppdatera sajtinnehåll och CLAUDE.md

**Baserad på:** main

## Sammanfattning

Kärnan har släppt 0.12.0–0.14.0 medan repot pinnar `klartex==0.11.1` och sajtinnehållet beskriver ~0.11-läget. Planen bumpar pinnen på båda ställena (pyproject + Dockerfile), verifierar backend mot 0.12.0:s breaking changes (genomgången visar att ingen kod behöver ändras — `signatures`-heuristiken används inte och felsträngar parsas inte), dokumenterar 0.13.0:s `asset_dir`-beteenden i page-template-registret, handkorrigerar mall- och blocktyplistorna i `index.html`/`llms.txt` (inkl. att ta bort tre påhittade blocktyper och det borttagna `klartex serve`-exemplet), och skriver om CLAUDE.md:s kärnprincip så den pekar på `backend/` i stället för kärnans borttagna HTTP-server.

## Triageringsstatus

| Fält | Värde |
|------|-------|
| **Redo att arbeta** | Ja |
| **Risk** | Låg |
| **Säker för junior** | Ja |

## Plangranskning

**Status:** Granskad
**Granskad:** 2026-08-27
**Feedback:** Codex-granskningen ledde till: korrigerad felaktig `detail.path`-utsaga (blockvalideringsfel bär bara `message`) plus nytt test som bevisar `body[0]`-passthrough, backend-versionbump 0.2.1 → 0.2.2, skärpt asset-dokumentation (ingen `../`-rekommendation, exakt filnamn-vs-`./`-semantik), faktaverifiering mot taggen `v0.14.0` i stället för kärnans working tree, merge-ordningsnotis mot #15, samt `-rs`/`pip check` i verifieringen.

## Relaterade filer

- [plan.md](plan.md) — Fullständig implementationsplan
- [progress.md](progress.md) — Implementationsframsteg
- [research.md](research.md) — Forskningsresultat (om finns)

## Relaterade issues

- #21 — Generera llms.txt från API:t (långsiktiga fixen för de handunderhållna listorna; utanför scope här)
- #22 — PLAN.md föråldrad (PLAN.md-uppdateringar lämnas dit)
- #15 — API_TOKEN-auth (rör `page_template_router.py` på egen gren; ingen radkonflikt med denna plan)
