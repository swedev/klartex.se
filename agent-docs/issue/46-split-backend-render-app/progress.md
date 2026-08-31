# Framsteg: Issue #46 — Split the backend into a render service and an app service

**Påbörjad:** 2026-08-30
**Senast uppdaterad:** 2026-08-31
**Status:** PR 0 mergad (#66); PR 2a implementerad på `issue/46-split-backend-render-app-r4`; PR 2b återstår

## Genomförda steg

- [x] **Fas 0 (PR 0): deploybarheten återställd.** Stacken är tillbaka i `v0.5.0`:s form — `backend` och `caddy`, inga render-referenser. Mergad som #66.
  - `render/` borttagen i sin helhet — render-tjänsten byggs av `swedev/klartex`, inte här.
  - `infra/docker-compose.yml`: tjänsten `render` och det interna nätverket `render` borta; `backend` på ett enda nätverk med taken 2560m / 1.5 CPU.
  - `.github/workflows/deploy.yml`: `render-v*`-triggern och `resolve`-jobbet borta; ett `v*`-flöde med jobben `build` och `deploy`.
  - `.github/workflows/ci.yml`: matrisen och `pins`-jobbet borta; ett `test`-jobb mot `backend/`.
  - `infra/.env.example`: `RENDER_VERSION` borta.
  - `infra/README.md`: alla render-referenser borta.

- [x] **Fas 1 (PR 2a): ikapp kärnan på den monolitiska imagen.** Kärnreleasen `klartex 0.17.0` bär både alias-borttagningen (swedev/klartex#80) och `klartex serve` + render-imagen (swedev/klartex#81), så blockeraren är löst.
  - `backend/pyproject.toml` och `backend/Dockerfile`: `klartex==0.17.0`. Basimagen är oförändrad — kärnans egen 0.17.0-release gate:ades mot samma `klartex-base:20260828-3`-pin.
  - `backend/src/klartex_se/render.py`: `BUILTIN_PAGE_TEMPLATES` raderad; `page_template` är `str | dict | None`, där objektet skickas rakt igenom som `data.page_template` och strängen slår upp en registrerad bundle. Anropet till kärnan skickar `header_source` i stället för `page_template_source`.
  - Shimmen (Designbeslut 11): bundlens `page_template.tex.jinja` skickas som `header_source` och `data.page_template.footer` sätts till `null`. Övriga inställningar i `data.page_template` behålls; ett anropar-skickat `footer` får ge vika.
  - `backend/tests/test_render.py`: alias-testet ersatt av objekt-passthrough (kwargs och `data`), kärnvalidering av en trasig slot-form, bundle → `header_source` + `asset_dir` + `footer: null`, footer-företrädet, och två xelatex-gatade tester som renderar objektformen respektive en registrerad bundle.
  - `backend/README.md`: nytt avsnitt "Sidmall på `/api/render`" med de två formerna och shimmens företräde; `unknown_page_template`-raden i felsvarstabellen nämner inte längre inbyggda mallar.
  - `llms.txt`: slot-formen (varianter, fält, defaults per yta) ersätter den gamla `name`-baserade beskrivningen; toppnivåns `page_template` tar nu även objekt, och bundlens footer-företräde är dokumenterat.
  - Verifierat: `pytest -q -rs` grönt i `backend/` (79 tester med xelatex, 76 + 3 skippade utan). Shimmen ger samma sida som före pin-bumpen — samma bundle renderad med 0.15 (`page_template_source`) och 0.17 (`header_source` + `footer: null`) ger identisk `pdftotext -layout`-utdata och identiska content streams; skillnaderna sitter enbart i fontsubset-taggar och xref-offsets.

## Pågående arbete

Inget. PR 2a ligger komplett på `issue/46-split-backend-render-app-r4` och stänger inget issue (`Refs #46`).

## Återstår

- **Fas 2 (PR 2b)** — proxy och konsumtion: `render_client.py`, `render.py` utan kompilering, `load_bundle_payload`, version 0.6.0, slim-Dockerfile, `test_render_client.py` och `test_contract.py`, `render`-tjänsten från `ghcr.io/swedev/klartex-render:${KLARTEX_VERSION}` med internt nät och härdning, `KLARTEX_VERSION` avledd ur backendens `klartex==`-pin och skriven till serverns `.env` av varje backend-deploy, tvåcontainer-smoke i `deploy.yml`, Caddy 180 s och docs i nu-state. Kräver att imagen finns publik på GHCR. Bär `Closes #46, closes #47`.
- **Fas 3** — utrullning av `v0.6.0`, verifiering på servern och minnesmätning med `docker stats`; taken justeras i en följdcommit.

## Anteckningar

- Runda 2 av det gamla tvåseriedesignet ligger som WIP-commit `20cb728` på `issue/46-split-backend-render-app-r2`. `render_client.py`, proxyn, `load_bundle_payload`, slim-Dockerfilen och kontraktstesterna där är avsedda att återanvändas i PR 2b, anpassade till kärnans slot-API och `klartex.server`.
- Appversionen står kvar på `0.5.0`. Planen lägger bumpen till `0.6.0` i PR 2b, så en `v0.5.x`-tagg från `main` mellan de två PR:erna skulle släppa kontraktsbytet under en patchversion.
- `page_template` som sträng med ett namn utanför `[a-z0-9][a-z0-9-]{0,63}` ger `500`: `get_bundle_path` kastar `PageTemplateError`, och endpointen fångar bara `PageTemplateNotFound`. Felet är oförändrat sedan före den här planen och ligger utanför Fas 1.
- Verifieringspunkter som kräver `docker build`, en lokal compose-uppstart eller produktionsmiljön hör till Fas 2 och 3 och är inte körda här.
