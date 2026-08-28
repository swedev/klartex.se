# Framsteg: Issue #32 — CI: stop rebuilding the 7 GB TeX Live image on every release

**Påbörjad:** 2026-08-28
**Senast uppdaterad:** 2026-08-28
**Status:** Pågår

## Genomförda steg

### Fas 1: Basimage och basworkflow (PR 1)

- [x] Fas 1, steg 1: Skapa `backend/Dockerfile.base` med de tunga lagren (TeX Live-bas, apt-paket, mscorefonts, texlive-bin-symlänk, sanity-check)
- [x] Fas 1, steg 2: Skapa `.github/workflows/backend-base.yml` (multi-arch build + push till `ghcr.io/swedev/klartex-se-base`)
- [x] Fas 1, steg 3: Exkludera `backend/Dockerfile.base` ur `paths`-filtret i `.github/workflows/backend.yml`
- [x] Fas 1, steg 4: Efter merge — bastagg verifierad i GHCR, paketsynlighet publik, tagg + manifest-digest noterade i planen

### Fas 2: Slimmad app-Dockerfile och workflow-justering (PR 2)

- [x] Fas 2, steg 1: Skriv om `backend/Dockerfile` (`FROM <bastagg@digest>`, ta bort flyttade lager och oanvänd `COPY pyproject.toml`)
- [ ] Fas 2, steg 2: Verifiera lokalt (docker build + render ur smoke-testet) — går inte i den här miljön, se Anteckningar
- [x] Fas 2, steg 3: Uppdatera `backend/README.md` (Docker- och Deploy-sektionerna)
- [x] Fas 2, steg 4: Uppdatera stale dok i `PLAN.md` och kommentaren i `.github/workflows/deploy.yml`
- [ ] Fas 2, steg 5: Verifiera efter merge att release-bygget går på ett par minuter

## Pågående arbete

Fas 2 är implementerad på branchen `issue/32-ci-texlive-base-image`: `backend/Dockerfile` är slimmad till `FROM ghcr.io/swedev/klartex-se-base:20260828-1@sha256:640992…` plus venv och `COPY src/`, `backend/README.md` beskriver bas-/app-uppdelningen och bump-proceduren, `PLAN.md`:s **API-image**-rad och huvudkommentaren i `.github/workflows/deploy.yml` är uppdaterade. Kvar: lokal docker-verifiering (steg 2) och efterkontroll av release-byggets tid (steg 5).

## Anteckningar

Bastaggen är kontrollerad direkt mot GHCR:s registry-API i stället för `docker buildx imagetools inspect` (ingen docker-daemon här): `ghcr.io/swedev/klartex-se-base:20260828-1` svarar `200` för en anonym pull-token, manifest-digesten är `sha256:640992b132b9880eb0f801b81ac5f30ea64190243fa8900fbfda098cb158562b` — samma som `FROM`-pinnen — och indexet listar `linux/amd64` och `linux/arm64`. Anonym token bekräftar också att paketet är publikt.

Fas 2, steg 2 (lokalt `docker build` + render ur smoke-testet) kunde inte köras: docker-daemonen kör inte i den här miljön. Skyddsnätet enligt planen gäller — `backend.yml` kör pytest, bygger amd64, startar containern och renderar en PDF innan någon image pushas, så en trasig bas ger röd CI i stället för en trasig release. Samma steg täcker även checklistans punkt om kontrollerad lager-invalidering, som kräver två lokala byggen.

`actionlint` på `.github/workflows/deploy.yml` rapporterar en SC2086-info på rad 93 — den finns redan på `main` och rör inte kommentarsändringen. `backend.yml` och `backend-base.yml` är rena.
