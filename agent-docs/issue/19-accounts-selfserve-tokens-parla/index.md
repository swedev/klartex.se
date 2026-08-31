# Issue #19: Accounts and self-serve API tokens via parla (replaces the Clerk track)

**Baserad på:** main

## Sammanfattning

Ersätter den delade `API_TOKEN`-miljövariabeln med konton och självbetjänade API-tokens byggda på `swedev-parla`. Fem faser: (1) Postgres + alembic + migrationsmedveten deploy (preflight → stop → dump → migrate → start, forward-only), (2) konton med e-post + sexsiffrig engångskod i tuttis form, (3) parlas providerhalva med device flow, scope-buren auktorisation (`render:write`, `page-templates:write`), `token_prefix='kx_'` och minimala serverrenderade `/pair`- och `/login`-sidor — varvid `API_TOKEN`-sökvägen tas bort, (4) verifiering i familjen (kräver parla-katalogrättelse till `https://app.klartex.se/api` och bump av styrlas pin), (5) tokens-/anslutningsvy i frontenden efter #14.

## Triageringsstatus

| Fält | Värde |
|------|-------|
| **Redo att arbeta** | Ja (fas 1–3; fas 4 kräver parla-katalogrättelse + styrla-bump, fas 5 väntar på #14) |
| **Risk** | Hög |
| **Säker för junior** | Nej |

## Plangranskning

**Status:** Granskad
**Granskad:** 2026-08-31
**Feedback:** Codex-granskningen fann fyra blockerare som alla arbetats in: parlas URL-kontrakt kräver katalogrättelse till `https://app.klartex.se/api` (+ styrla-pin-bump före fas 4), en `/login`-sida behövs bredvid `/pair`, scope-kontrollen måste skiljas från tier (parla-users passerar `require_scope` implicit; `latex` kräver uttryckligen `render:write`; approve-guarden ligger på beviljade scopes), och deploy-ordningen standardiserades till preflight → stop → dump → migrate → start med dumpar utanför rsync-målet och utan automatisk gammal-image-restart efter lyckad migration. Därtill schemadetaljer, per-IP-strypning av `request-code`, radstädning, migrationstester och `PARLA_REPO_TOKEN` på alla tre installationsvägarna; konfliktrisken höjdes till Medel (#14, #21).

## Relaterade filer

- [plan.md](plan.md) — Fullständig implementationsplan
- [progress.md](progress.md) — Implementationsframsteg
- [research.md](research.md) — Forskningsresultat (om finns)

## Relaterade issues

- #23 — Anonym rate-limitad nivå på /render; token är uppgraderingsvägen, delar tier-/scope-ytan
- #20 — Härdning av /render; repo-lokala delen i praktiken klar, `latex`-blockets policy berörs av scope-modellen
- #14 — Frontend-scaffold (omergad gren); förkrav för fas 5 och full stängning av #19
- #21 — llms.txt-innehåll; `TOKEN_HOWTO`-texten ändras här
- #15 — Stängd föregångare: `API_TOKEN`-stopgapen som denna plan avvecklar
