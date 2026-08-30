# Issue #15: Auth: API_TOKEN for writes and the extended surface (replaces ADMIN_TOKEN) — stopgap until self-serve tokens exist

**Baserad på:** main

## Sammanfattning

`ADMIN_TOKEN` ersätts av `API_TOKEN`, och `/api/render` får en tier-medveten dependency i stället för en gate: anonyma anrop tillåts som idag men `latex`-blocket (rå LaTeX) kräver token och svarar `403 token_required` med `path`, `block_type` och en `message` som säger hur man får en token. Writes på `/api/page-templates` kräver token som förut, nu med strukturerade `401`/`503`-kroppar. Rename genomförs i backend, tester, compose, `.env.example`, infra-README och `PLAN.md`; `deploy.yml` preflightar att serverns `.env` har `API_TOKEN=` innan rsync. Dokumentationen (`backend/README.md`, `llms.txt`, `index.html`) beskriver den nya uppdelningen. Kvot per tier, bundle-spärr och `429` lämnas till #23; self-serve-tokens är #19.

## Triageringsstatus

| Fält | Värde |
|------|-------|
| **Redo att arbeta** | Ja |
| **Risk** | Medel |
| **Säker för junior** | Nej |

## Plangranskning

**Status:** Granskad
**Granskad:** 2026-08-30
**Feedback:** Codex-granskning tillämpad: `latex`-skanningen begränsad till `template == "_block"` och `data["body"]`, iterativ i stället för rekursiv, med regressionstest för recept-mallar; `WWW-Authenticate` bort från `403`; `503`-beskrivningen på `/api/render` täcker både `overloaded` och `token_not_configured`; README-noten rättad (writes ger `401`/`503`, aldrig `403`); båda styckena under "Vad som är öppet" i `index.html` skrivs om; CI-beskrivningen rättad (hela sviten körs, bara `needs_xelatex` skippar); deploy-preflighten kräver icke-tomt värde; rollback-kompatibilitet (`ADMIN_TOKEN` kvar i `.env` under fönstret); fler tester (DELETE, prioritet 401/503 före 403, tom/icke-ASCII token, discovery öppet, OpenAPI). Triagen rättad: #20 och #21 är öppna, #19 blockeras inte, PR:en ska `Refs #23`. Designbeslut 3 (token på förfrågan via kontakt@klartex.se) kvarstår som produktbeslut att bekräfta — den delade tokenen ger också write/delete på alla bundles.

## Relaterade filer

- [plan.md](plan.md) — Fullständig implementationsplan
- [progress.md](progress.md) — Implementationsframsteg
- [research.md](research.md) — Forskningsresultat (om finns)

## Relaterade issues

- #19 — Konton och self-serve-tokens via parla; ersätter den delade tokenen som införs här
- #20 — Härdning av `/render` (rate limit, resurstak); mergad via PR #25, förutsättningen för att öppna `latex`-spärren här
- #23 — Anonym rate-limitad tier; bygger på `Tier`-dependencyn från detta issue och tar kvot, bundle-spärr och `429`
- PR #16 — Stängd utan merge (gate:ade hela `/render`); branchen raderad, inget att återanvända
