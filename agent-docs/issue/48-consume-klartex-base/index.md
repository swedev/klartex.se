# Issue #48: Consume ghcr.io/swedev/klartex-base: remove local base image build

**Baserad på:** main

## Sammanfattning

Basimagen byggs och publiceras numera från `swedev/klartex` som `ghcr.io/swedev/klartex-base`, med klartex-testsviten körd i imagen före varje push. Kopian i detta repo är superseded: `backend/Dockerfile.base` och `.github/workflows/backend-base.yml` raderas, `backend/Dockerfile`s `FROM`-pin pekas om till `ghcr.io/swedev/klartex-base:20260828-3@<digest>` (tagg + digest ur issuet), och `backend/README.md` + `PLAN.md` uppdateras att beskriva det nya bump-flödet. Publicerade `klartex-se-base`-taggar på GHCR lämnas orörda — historiken refererar dem.

## Triageringsstatus

| Fält | Värde |
|------|-------|
| **Redo att arbeta** | Ja |
| **Risk** | Låg |
| **Säker för junior** | Ja |

## Plangranskning

**Status:** Granskad
**Granskad:** 2026-08-28
**Feedback:** Granskningen lade till en obligatorisk fas 0 (verifiera pin, plattformar och anonym pull mot GHCR via `imagetools inspect`), korrigerade verifieringsgreppen så de inte slår på legitima uppströmsreferenser, preciserade att uppströmstestsviten körs i amd64-imagen (arm64 täcks av sanity-checken — accepterad kvarstående risk) samt att step-summaryn skriver image-referensen, inte en `FROM`-rad. Triagen för #20 uppdaterad: implementationen landade i PR #25, ingen aktiv konflikt.

## Relaterade filer

- [plan.md](plan.md) — Fullständig implementationsplan
- [progress.md](progress.md) — Implementationsframsteg
- [research.md](research.md) — Forskningsresultat (om finns)

## Relaterade issues

- #32 — CI: stop rebuilding the 7 GB TeX Live image on every release (stängt — införde det lokala basbygge som nu tas bort)
- swedev/klartex#55 — refereras i issuet; basbygget deferrades därifrån och levererades i swedev/klartex#56 och #57
