# Framsteg: Issue #19 — Accounts and self-serve API tokens via parla

**Påbörjad:** 2026-08-31
**Senast uppdaterad:** 2026-08-31
**Status:** Fas 2 klar

## Genomförda steg

- [x] Fas 1, steg 1: Databasmodul och alembic-miljö
- [x] Fas 1, steg 2: Migrationstester i CI mot riktig Postgres
- [x] Fas 1, steg 3: Postgres i produktionsstacken
- [x] Fas 1, steg 4: Deploy-sekvensen preflight → stop → dump → migrate → start
- [x] Fas 1, steg 5: Smoke-testet i release-bygget får databas
- [x] Fas 2, steg 1: Modeller och migration `0001_accounts`
- [x] Fas 2, steg 2: Auth-endpoints — e-post + engångskod, sessioner
- [x] Fas 2, steg 3: Konfiguration
- [ ] Fas 3: Parlas providerhalva — device flow, scopes, `API_TOKEN` bort
- [ ] Fas 4: Verifiering i familjen
- [ ] Fas 5: Tokens-/anslutningsvy i frontenden (efter #14)

## Pågående arbete

Fas 1 ligger på `main` via PR #72. Fas 2 (konton) ligger på
`issue/19-accounts-selfserve-tokens-parla-r2`. Nästa omgång är fas 3.

## Anteckningar

Planen delar upp arbetet i fem faser som var för sig är en PR (`Part of #19`).

Fas 3 kan inte påbörjas här: dess steg 0 kräver en PR mot `swedev/parla` som
rättar `api_base_url` till `https://app.klartex.se/api`, och designbeslut 4
(vem som godkänner en parkoppling) är märkt "måste bekräftas före
implementation av fas 3". Fas 4 väntar på att styrlas parla-pin bumpas, fas 5
på #14.
