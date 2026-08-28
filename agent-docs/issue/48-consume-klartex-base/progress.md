# Framsteg: Issue #48 — Consume ghcr.io/swedev/klartex-base: remove local base image build

**Påbörjad:** 2026-08-28
**Senast uppdaterad:** 2026-08-28
**Slutförd:** 2026-08-28
**Status:** Slutförd

## Genomförda steg

- [x] Fas 0, steg 1: Verifiera pinnen mot GHCR (`docker buildx imagetools inspect`)
- [x] Fas 1, steg 1: Radera `backend/Dockerfile.base`
- [x] Fas 1, steg 2: Radera `.github/workflows/backend-base.yml`
- [x] Fas 2, steg 1: Peka om `FROM`-raden i `backend/Dockerfile`
- [x] Fas 2, steg 2: Skriv om huvudkommentaren i `backend/Dockerfile`
- [x] Fas 3, steg 1: `backend/README.md` — Docker-avsnittet
- [x] Fas 3, steg 2: `backend/README.md` — "Bumpa basimagen"
- [x] Fas 3, steg 3: `PLAN.md` — beslutstabellens API-image- och Bygge och deploy-rader

## Verifiering

- [x] Fas 0: `docker buildx imagetools inspect ghcr.io/swedev/klartex-base:20260828-3` lyckades utan inloggning (inga ghcr.io-credentials lagrade), digesten är exakt `sha256:b011056413d449bdc41b893ff1bd538a2be46d78d3794698eb134f45936d6ff2`, och manifestet innehåller både `linux/amd64` och `linux/arm64` (plus attestation-manifest per plattform)
- [x] `test ! -e backend/Dockerfile.base && test ! -e .github/workflows/backend-base.yml`
- [x] `grep -rn 'klartex-se-base\|backend/Dockerfile\.base\|backend-base\.yml' backend/ .github/ PLAN.md index.html llms.txt` ger noll träffar
- [x] `FROM`-pinnen i `backend/Dockerfile` är exakt `ghcr.io/swedev/klartex-base:20260828-3@sha256:b011056413d449bdc41b893ff1bd538a2be46d78d3794698eb134f45936d6ff2`
- [x] `backend/README.md`s bump-procedur beskriver flödet via `swedev/klartex` med image-referensen ur `base-image.yml`-körningens step-summary
- [x] Dokumentationen är skriven i nu-läge
- [x] `ci.yml` är Docker-fri och refererar inte det raderade workflowet; `deploy.yml` har ingen `workflow_run`-koppling till det. Båda workflows parsar som giltig YAML.
- [ ] (Valfritt, hoppat över: ~7 GB pull) `docker build -t klartex-se-backend:dev backend/`. Accepterad kvarstående risk enligt planen — första fullständiga app-bygget mot den nya basen sker i release-workflowns smoke-test vid nästa `v*`-tagg.

## Anteckningar

- De kvarvarande träffarna på `Dockerfile.base` i `backend/Dockerfile` och `backend/README.md` är referenser till uppströms `docker/Dockerfile.base` i `swedev/klartex` — legitima enligt planen.
- Publicerade taggar under `ghcr.io/swedev/klartex-se-base` är orörda på GHCR (designbeslut 2).
