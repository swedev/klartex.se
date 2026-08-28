# Issue #32: CI: stop rebuilding the 7 GB TeX Live image on every release

**Baserad på:** main

## Sammanfattning

Varje release bygger om den ~7 GB stora TeX Live-imagen (~15 min QEMU-arm64) eftersom GHA-cachen evictar de tunga lagren och en oanvänd `COPY pyproject.toml` invaliderar venv-lagret vid varje versionsbump. Planen bryter ut de tunga lagren till en basimage `ghcr.io/swedev/klartex-se-base` (`backend/Dockerfile.base` + egen workflow som bara triggar när basen ändras), slimmar app-Dockerfilen till `FROM <bastagg@digest>` + venv + `COPY src/`, och tar bort den onödiga COPY-raden. Utrullning i två PR:er: basen först (taggen måste finnas i GHCR), sedan den slimmade app-Dockerfilen.

## Triageringsstatus

| Fält | Värde |
|------|-------|
| **Redo att arbeta** | Ja |
| **Risk** | Medel |
| **Säker för junior** | Nej |

## Plangranskning

**Status:** Granskad
**Granskad:** 2026-08-28
**Feedback:** Två granskningspass. Tillämpat: immutabel bastagg via digest-pin (`<tagg>@sha256:<digest>`, ingen `latest`), sanity-check-lager i basen (absoluta sökvägar — TeX-binärer saknas i `PATH`), `paths`-exkluderingen flyttad till PR 1 (med not om att PR 1 ändå triggar ett sista app-bygge via workflow-filens egen path-match), stale dok i `PLAN.md`/`deploy.yml`-kommentaren tillagd i scope, operativa förutsättningar i triagen, samt kontrollerad verifiering av lager-invalidering.

## Relaterade filer

- [plan.md](plan.md) — Fullständig implementationsplan
- [progress.md](progress.md) — Implementationsframsteg
- [research.md](research.md) — Forskningsresultat (om finns)

## Relaterade issues

- #20 — Öppen; dess plan rör också `.github/workflows/backend.yml`, men den ändringen (pytest-steg) finns redan på `main` — låg konfliktrisk
