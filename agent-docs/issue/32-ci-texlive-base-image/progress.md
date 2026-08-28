# Framsteg: Issue #32 — CI: stop rebuilding the 7 GB TeX Live image on every release

**Påbörjad:** 2026-08-28
**Senast uppdaterad:** 2026-08-28
**Status:** Pågår

## Genomförda steg

### Fas 1: Basimage och basworkflow (PR 1)

- [x] Fas 1, steg 1: Skapa `backend/Dockerfile.base` med de tunga lagren (TeX Live-bas, apt-paket, mscorefonts, texlive-bin-symlänk, sanity-check)
- [x] Fas 1, steg 2: Skapa `.github/workflows/backend-base.yml` (multi-arch build + push till `ghcr.io/swedev/klartex-se-base`)
- [x] Fas 1, steg 3: Exkludera `backend/Dockerfile.base` ur `paths`-filtret i `.github/workflows/backend.yml`
- [ ] Fas 1, steg 4: Efter merge — verifiera bastagg i GHCR, sätt paketsynlighet, notera tagg + manifest-digest

### Fas 2: Slimmad app-Dockerfile och workflow-justering (PR 2)

- [ ] Fas 2, steg 1: Skriv om `backend/Dockerfile` (`FROM <bastagg@digest>`, ta bort flyttade lager och oanvänd `COPY pyproject.toml`)
- [ ] Fas 2, steg 2: Verifiera lokalt (docker build + render ur smoke-testet)
- [ ] Fas 2, steg 3: Uppdatera `backend/README.md` (Docker- och Deploy-sektionerna)
- [ ] Fas 2, steg 4: Uppdatera stale dok i `PLAN.md` och kommentaren i `.github/workflows/deploy.yml`
- [ ] Fas 2, steg 5: Verifiera efter merge att release-bygget går på ett par minuter

## Pågående arbete

Fas 1 (PR 1) är implementerad. Nästa steg är fas 1, steg 4 — verifiering efter merge: bastaggen måste finnas i GHCR med båda arkitekturerna, paketsynligheten sättas, och tagg + manifest-digest noteras. Fas 2 påbörjas därefter i en egen PR.

## Anteckningar

Lokal verifiering av `Dockerfile.base` gjordes inte: docker-daemonen kör inte i den här miljön, och ett fullt basbygge är ~7 GB och ~15–20 min per arkitektur. Lagren är flyttade oförändrade från `backend/Dockerfile`, som bygger grönt idag; det nya är sanity-check-lagret, som körs av basworkflown på båda arkitekturerna vid merge. `.github/workflows/backend-base.yml` och den ändrade `backend.yml` är validerade med `actionlint` (rent).

Utrullningen sker i två PR:er (designbeslut 2 i planen). Fas 2 kan inte påbörjas förrän PR 1 är mergad och basworkflown publicerat en tagg i GHCR — app-Dockerfilens `FROM`-rad måste pinna en tagg + manifest-digest som faktiskt existerar. Denna körning omfattar därför fas 1.
