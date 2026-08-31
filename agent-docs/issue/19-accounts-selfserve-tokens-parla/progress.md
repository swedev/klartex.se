# Framsteg: Issue #19 — Accounts and self-serve API tokens via parla

**Påbörjad:** 2026-08-31
**Senast uppdaterad:** 2026-08-31
**Status:** Fas 1 klar

## Genomförda steg

- [x] Fas 1, steg 1: Databasmodul och alembic-miljö
- [x] Fas 1, steg 2: Migrationstester i CI mot riktig Postgres
- [x] Fas 1, steg 3: Postgres i produktionsstacken
- [x] Fas 1, steg 4: Deploy-sekvensen preflight → stop → dump → migrate → start
- [x] Fas 1, steg 5: Smoke-testet i release-bygget får databas
- [ ] Fas 2: Konton — e-post + engångskod, sessioner, org
- [ ] Fas 3: Parlas providerhalva — device flow, scopes, `API_TOKEN` bort
- [ ] Fas 4: Verifiering i familjen
- [ ] Fas 5: Tokens-/anslutningsvy i frontenden (efter #14)

## Pågående arbete

Fas 1 är klar och ligger på `issue/19-accounts-selfserve-tokens-parla`.
Nästa omgång är fas 2 (konton).

## Anteckningar

Planen delar upp arbetet i fem faser som var för sig är en PR (`Part of #19`).
Denna omgång levererar fas 1 — Postgres, migrationsgrunden och den
migrationsmedvetna deployen — som planen kallar ett hårt förkrav för allt
senare.

Fas 3 kan inte påbörjas här: dess steg 0 kräver en PR mot `swedev/parla` som
rättar `api_base_url` till `https://app.klartex.se/api`, och designbeslut 4
(vem som godkänner en parkoppling) är märkt "måste bekräftas före
implementation av fas 3". Fas 4 väntar på att styrlas parla-pin bumpas, fas 5
på #14.
