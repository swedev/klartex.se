# Framsteg: Issue #46 — Split the backend into a render service and an app service

**Påbörjad:** 2026-08-30
**Senast uppdaterad:** 2026-08-30
**Status:** PR 0 implementerad; PR 2a och 2b blockerade av swedev/klartex#81

## Genomförda steg

- [x] **Fas 0 (PR 0): deploybarheten återställd.** Trädet är identiskt med `v0.5.0` utanför `agent-docs/`.
  - `render/` borttagen i sin helhet — render-tjänsten byggs av `swedev/klartex`, inte här.
  - `infra/docker-compose.yml`: tjänsten `render` och det interna nätverket `render` borta; `backend` på ett enda nätverk med taken 2560m / 1.5 CPU. `docker compose config` validerar med bara `BACKEND_VERSION` satt och `API_TOKEN` osatt.
  - `.github/workflows/deploy.yml`: `render-v*`-triggern och `resolve`-jobbet borta; ett `v*`-flöde med jobben `build` och `deploy`.
  - `.github/workflows/ci.yml`: matrisen och `pins`-jobbet borta; ett `test`-jobb mot `backend/`.
  - `infra/.env.example`: `RENDER_VERSION` borta.
  - `infra/README.md`: alla render-referenser borta (tabellrader, "Uppgradera", GHCR-avsnittet, säkerhet, felsökning).
  - Verifierat: `pytest -q -rs` i `backend/` (74 gröna), `docker compose config` med enbart `BACKEND_VERSION`, båda workflow-filerna parsar som YAML, och ingen fil utanför `agent-docs/` nämner `render-v`, `RENDER_VERSION`, `klartex-se-render` eller `render/`.

## Pågående arbete

Inget. PR 0 ligger komplett och stänger inget issue (`Refs #46`).

## Återstår

- **Fas 1 (PR 2a)** — kom ikapp kärnan på den monolitiska imagen: pin-bump till kärnreleasen från swedev/klartex#81, `header_source` i stället för `page_template_source`, aliasen `formal`/`clean`/`none` bort ur det publika API:t (`BUILTIN_PAGE_TEMPLATES` raderas, `page_template` blir `str | object`), shimmen som skickar monolitiska bundlar som `header_source` med `footer: null`, och rensning av alias-namnen ur `llms.txt`, `index.html`, README och `RenderRequest`-exemplen. Kräver att kärnreleasen finns på PyPI.
- **Fas 2 (PR 2b)** — proxy och konsumtion: `render_client.py`, `render.py` utan kompilering, `load_bundle_payload`, version 0.6.0, slim-Dockerfile, `test_render_client.py` och `test_contract.py`, `render`-tjänsten från `ghcr.io/swedev/klartex-render:${KLARTEX_VERSION}` med internt nät och härdning, `KLARTEX_VERSION` avledd ur backendens `klartex==`-pin och skriven till serverns `.env` av varje backend-deploy, tvåcontainer-smoke i `deploy.yml`, Caddy 180 s och docs i nu-state. Kräver att imagen finns publik på GHCR. Bär `Closes #46, closes #47`.
- **Fas 3** — utrullning av `v0.6.0`, verifiering på servern och minnesmätning med `docker stats`; taken justeras i en följdcommit.

## Anteckningar

- Runda 2 av det gamla tvåseriedesignet ligger som WIP-commit `20cb728` på `issue/46-split-backend-render-app-r2`. `render_client.py`, proxyn, `load_bundle_payload`, slim-Dockerfilen och kontraktstesterna där är avsedda att återanvändas i PR 2b, anpassade till kärnans slot-API och `klartex.server`.
- Designbeslut 12 (tre PR:er) är skälet till att den här grenen stannar vid PR 0: 2a behöver kärnreleasen på PyPI och 2b dessutom imagen på GHCR.
- Verifieringspunkter som kräver `docker build`, en lokal compose-uppstart eller produktionsmiljön hör till Fas 2 och 3 och är inte körda här.
