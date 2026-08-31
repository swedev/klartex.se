# Framsteg: Issue #46 — Split the backend into a render service and an app service

**Påbörjad:** 2026-08-30
**Senast uppdaterad:** 2026-08-31
**Status:** PR 0 mergad (#66); PR 2a mergad (#67); PR 2b implementerad på `issue/46-split-backend-render-app-r5`

## Genomförda steg

- [x] **Fas 0 (PR 0): deploybarheten återställd.** Stacken är tillbaka i `v0.5.0`:s form — `backend` och `caddy`, inga render-referenser. Mergad som #66.
  - `render/` borttagen i sin helhet — render-tjänsten byggs av `swedev/klartex`, inte här.
  - `infra/docker-compose.yml`: tjänsten `render` och det interna nätverket `render` borta; `backend` på ett enda nätverk med taken 2560m / 1.5 CPU.
  - `.github/workflows/deploy.yml`: `render-v*`-triggern och `resolve`-jobbet borta; ett `v*`-flöde med jobben `build` och `deploy`.
  - `.github/workflows/ci.yml`: matrisen och `pins`-jobbet borta; ett `test`-jobb mot `backend/`.
  - `infra/.env.example`: `RENDER_VERSION` borta.
  - `infra/README.md`: alla render-referenser borta.

- [x] **Fas 1 (PR 2a): ikapp kärnan på den monolitiska imagen.** Kärnreleasen `klartex 0.17.0` bär både alias-borttagningen (swedev/klartex#80) och `klartex serve` + render-imagen (swedev/klartex#81). Mergad som #67.
  - `backend/pyproject.toml` och `backend/Dockerfile`: `klartex==0.17.0`.
  - `backend/src/klartex_se/render.py`: `BUILTIN_PAGE_TEMPLATES` raderad; `page_template` är `str | dict | None`, där objektet skickas rakt igenom som `data.page_template` och strängen slår upp en registrerad bundle. Anropet till kärnan skickar `header_source`.
  - Shimmen (Designbeslut 11): bundlens `page_template.tex.jinja` skickas som `header_source` och `data.page_template.footer` sätts till `null`. Dokumentinställningarna i `data.page_template` behålls; både `header` och `footer` som anropet skickar får ge vika.
  - `backend/README.md` och `llms.txt`: slot-formen dokumenterad, alias-namnen borta.

- [x] **Fas 2 (PR 2b): proxy, slim image och konsumtion av render-imagen.**
  - `backend/src/klartex_se/render_client.py` (ny): `RENDER_URL`, `RenderUpstreamError`, `render_pdf(template, data, header_source, footer_source, assets)`, modulglobal `httpx.Client` bakom `_client()`, tidsbudget `Timeout(connect=5, read=130, write=30, pool=5)`. Passthrough för {400, 500, 503} med en `detail` av rätt form plus `Retry-After`; allt annat, inklusive `httpx.TransportError`, blir `502 render_unavailable` med generiskt meddelande.
  - `backend/src/klartex_se/render.py`: kompileringen, felmappningen, `_block_error_path` och `_BLOCK_ERROR_RE` borta. `MAX_INFLIGHT_RENDERS = 2` tas före bundle-laddningen, så semaforen täcker både payload-bygget och proxy-anropet. `RenderUpstreamError` → `HTTPException` med status, detail och headers; `responses` dokumenterar 502.
  - `backend/src/klartex_se/page_templates.py`: `load_bundle_payload(name) -> (source, assets som base64)`. Saknad asset, källa som inte är UTF-8, eller ett asset-namn som inte matchar `ASSET_NAME_RE` ger `PageTemplateError` → 400 `input_error`.
  - `backend/src/klartex_se/main.py`: `/api/health` rapporterar även `klartex`.
  - `backend/pyproject.toml` + `__init__.py`: version `0.6.0`; `httpx>=0.27` som huvudberoende; `klartex[serve]` i `dev`-extran.
  - `backend/Dockerfile`: `FROM python:3.12-slim`, installation ur `pyproject.toml`, `HEALTHCHECK` via `urllib`.
  - Tester: `test_render_client.py` (ny, `httpx.MockTransport`), `test_contract.py` (ny, `_client()` → `TestClient(klartex.server.app)`), `test_page_templates.py` (`load_bundle_payload` inkl. trasiga bundles), `test_render.py` omskriven kring proxyn.
  - `infra/docker-compose.yml`: `render` från `ghcr.io/swedev/klartex-render:${KLARTEX_VERSION:?}`, internt nät utan gateway, `depends_on: service_healthy`, `no-new-privileges`, `cap_drop: ALL`, `read_only`, tmpfs för `/tmp` och `/home/render`; taken `render` 1792m / 1.5 CPU / 256 pids och `backend` 768m / 0.5 CPU / 128 pids.
  - `infra/.env.example`: `KLARTEX_VERSION=0.17.0`, `BACKEND_VERSION=0.6.0`.
  - `infra/Caddyfile`: `response_header_timeout` 180 s.
  - `.github/workflows/ci.yml`: steg som felar om `.env.example` och `klartex==`-pinnen skiljer sig.
  - `.github/workflows/deploy.yml`: kärn-pinnen avleds i `Resolve versions`; tvåcontainer-smoke med render-imagen på ett tillfälligt nät; deployen skriver båda `.env`-raderna, pullar `backend render`, kräver `backend render caddy` igång, jämför health-versionerna och kör ett riktigt `/api/render` under återställningstrappen.
  - Docs i nu-state: `backend/README.md`, `infra/README.md`, `PLAN.md`, `CLAUDE.md`.

## Pågående arbete

Inget. PR 2b ligger komplett på `issue/46-split-backend-render-app-r5` och bär `Closes #46, closes #47`.

## Återstår

- **Fas 3** — utrullning av `v0.6.0` och verifiering på servern: `docker compose exec render env` utan `API_TOKEN`, utgående trafik blockerad, `docker stats` under en riktig rendering, och taken justerade i en följdcommit om mätningen kräver det. Uppdatera #19 med att `backend` är platsen för Postgres/parla.

## Anteckningar

- Verifierat lokalt med de två riktiga containrarna (`ghcr.io/swedev/klartex-render:0.17.0` plus en `docker build` av `backend/`) på ett `internal`-nätverk med hela härdningen: health på båda, `/api/templates`, minimal render, registrerad bundle med logotyp-asset, slot-objekt, anonymt `latex`-block → 403, och `502 render_unavailable` med render-containern stoppad. Fontconfig loggar ingenting om skrivbara cache-kataloger, `curl` ut från render-containern misslyckas, och dess miljö saknar `API_TOKEN`.
- `docker stats` under fem sekventiella renders: `render` 251 MiB / 100 % CPU, `backend` 49 MiB / 0,2 % CPU. Taken 1792m respektive 768m har alltså god marginal på den lasten; mätningen på servern (Fas 3) är den som gäller för beslutet i #19.
- Backend-imagen väger 312 MB (arm64) mot monolitens 8,83 GB. Planens checklista gissade "under ~200 MB"; skillnaden är `uvicorn[standard]` och pydantic/jsonschema ovanpå `python:3.12-slim`.
- Passthrough-mängden är {400, 500, 503} enligt planen. Kärnans `413 payload_too_large` faller därmed till `502`. Caddy kapar render-bodyn vid 2 MB och kärnans gräns är 80 MB, så det svaret nås inte i drift.
- `page_template` som sträng med ett namn utanför `[a-z0-9][a-z0-9-]{0,63}` ger `500`: `get_bundle_path` kastar `PageTemplateError`, och endpointen fångar bara `PageTemplateNotFound`. Felet är oförändrat sedan före den här planen.
- Runda 2 av det gamla tvåseriedesignet ligger som WIP-commit `20cb728` på `issue/46-split-backend-render-app-r2`. Den grenen är förbrukad — allt återanvändbart därifrån ligger i den här rundan.
