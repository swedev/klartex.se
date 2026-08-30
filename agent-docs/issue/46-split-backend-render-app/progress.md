# Framsteg: Issue #46 — Split the backend into a render service and an app service

**Påbörjad:** 2026-08-30
**Senast uppdaterad:** 2026-08-30
**Status:** Fas 1 klar (PR 1); Fas 2–4 återstår

## Genomförda steg

- [x] Fas 1, steg 1: `render/` skapad som eget Python-projekt. `pyproject.toml` (`klartex-se-render` 0.1.0, `klartex==0.15.0` — samma pin som backend), `src/klartex_render/__init__.py`, `main.py` (FastAPI utan docs/openapi, `GET /health` med `status`/`version`/`klartex`, middleware som avvisar `Content-Length` över `MAX_REQUEST_BYTES` = 80 MB med 413 innan kroppen läses) och `render.py` (`RenderRequest` med `template`/`data`/`page_template_source`/`assets`, asset-validering mot samma `ASSET_NAME_RE` och samma gränser som registret, tempkatalog per anrop, `MAX_CONCURRENT_RENDERS = 2`, `_block_error_path` + `_BLOCK_ERROR_RE` och felmappningen flyttade hit ur `backend/src/klartex_se/render.py`).
- [x] Fas 1, steg 2: `render/tests/test_render.py` — 33 tester, alla gröna lokalt med xelatex på PATH. De kärnnära testerna kopierade från `backend/tests/test_render.py` (block-error-path i alla tre meddelandeformer, nästlade carriers, forgery-fallet, schema-path, semaforen inklusive tredje samtidiga anrop) plus nya för det inline-kontraktet: bundle med `logo.png` renderar, samma bundle utan assetet ger 500, temporärkatalogen är borta när svaret skrivits, ett anrop utan bundle skickar `asset_dir=None`, ogiltiga filnamn (`../`, `sub/`, dotfile, tomt, för långt) → 400, ogiltig base64 → 400, för stor asset → 400, för många assets → 400, för stor `page_template_source` → 400, för stor `Content-Length` → 413, inget OpenAPI-schema publiceras. `backend/tests/` orörd — monoliten förblir testad tills den byts i Fas 2.
- [x] Fas 1, steg 3: `render/Dockerfile` — samma `FROM ghcr.io/swedev/klartex-base`-pin (tagg + digest) som backend har idag, `COPY pyproject.toml` + `src/` följt av `pip install --no-cache-dir .` i venvet så pinnen finns på ett ställe, `HEALTHCHECK` mot `http://localhost:8000/health`, `uvicorn klartex_render.main:app`. Wheel-bygget verifierat lokalt (`pip install ./render` i ett tomt venv importerar `klartex_render`); själva image-bygget kräver 9 GB-basen och är inte kört här.
- [x] Fas 1, steg 4: `render/README.md` — syfte, kontraktet (`/health`, `/render`, request-formen, gränserna, felsvarstabellen), belastningstaket, lokal körning på port 8001, Docker och basimage-bump, deploy via `render-v*` och utrullningsordningen vid kärnbump. Bär uttryckligen att tjänsten aldrig ska exponeras publikt.
- [x] Fas 1, steg 5: compose, env och workflows.
  - `infra/docker-compose.yml`: tjänsten `render` (`${RENDER_VERSION:?…}`, inga `ports`, inga volymer, ingen `environment`, healthcheck, `restart: unless-stopped`), nätverket `render` med `internal: true`, `backend` på både `default` och `render`. Övergångstak enligt designbeslut 6: `render` 1536m/1.5 CPU, `backend` sänkt 2560m → 1792m. `docker compose config` validerar; utan `RENDER_VERSION` stannar den på den saknade variabeln med det avsedda meddelandet.
  - `infra/.env.example`: `RENDER_VERSION=0.1.0` med kommentar om den egna versionsserien.
  - `.github/workflows/deploy.yml`: trigger även på `render-v*`; nytt `resolve`-jobb som ur taggen härleder `service`, `version`, `image` och `env_var` och verifierar versionen mot rätt `pyproject.toml`; `build` och `deploy` parametriserade på dess outputs; smoke-testet väljer `/health`+`/render` eller `/api/health`+`/api/render`; deploy-steget skriver bara sin egen `.env`-rad, kontrollerar `backend render caddy`, verifierar den släppta tjänstens version (för `render` via `docker compose exec -T render curl`), kör ett riktigt render-anrop mot `render` medan `restore`-trappen är armerad, och skriver ut båda tjänsternas health-svar.
  - `.github/workflows/ci.yml`: matris `backend`/`render` plus jobbet `pins` som jämför `klartex==`-pinnarna. Båda run-blocken syntaxkontrollerade, pin-kontrollen körd lokalt (`klartex==0.15.0`).
- [x] Fas 1, steg 6: `infra/README.md` — tabellraderna för `docker-compose.yml`, `.env.example` och `deploy.yml`, en mening om stackens tre containrar, omskrivet "Uppgradera"-avsnitt (två serier, tabell, kärnbump i ordningen render → backend, felordningen stannar vid `pull`), GHCR-avsnittet täcker båda paketen inklusive synlighetsfällan, säkerhetsavsnittet beskriver `render` utan portar, volymer, hemligheter och egress, felsökningen får `logs render` och health via `docker compose exec`.

## Pågående arbete

Inget. Fas 1 ligger komplett på `issue/46-split-backend-render-app` och är avsedd som **PR 1**: den lägger till `render` bredvid monoliten utan att ändra något utåt.

## Återstår

- **Fas 2 (PR 2)** — `backend` blir policy-lagret: `render_client.py`, `render.py` utan kompilering, `load_bundle_payload` i `page_templates.py`, version 0.6.0, slim-Dockerfile, omskrivna och nya tester (`test_render_client.py`, `test_contract.py`), compose-ändringarna för `backend` (`RENDER_URL`, `depends_on`, slutgiltiga tak, python-healthcheck), tvåcontainer-smoke i `deploy.yml`, Caddyfile 150 s → 180 s.
- **Fas 3 (i PR 2)** — `backend/README.md`, `infra/README.md`, `PLAN.md`, `CLAUDE.md` i nu-state.
- **Fas 4** — utrullning: `render-v0.1.0` först, mätning av två samtidiga renders med `docker stats` innan PR 2 mergas (det avgör om 1792m i designbeslut 6 håller), sedan `v0.6.0`.

## Anteckningar

- Designbeslut 8 (två PR:er i utrullningsordning) är skälet till att den här grenen stannar vid Fas 1: PR 2 får inte mergas förrän `render-v0.1.0` ligger i produktion och minnesmätningen i Fas 4 steg 2 är gjord.
- Verifieringschecklistans punkter som kräver `docker build` av 9 GB-basen, en lokal compose-uppstart eller produktionsmiljön är inte körda här — de hör till Fas 4.
- PR 1 stänger inget issue: `Refs #46`. `Closes #46, closes #47` hör till PR 2.
