# Framsteg: Issue #46 — Split the backend into a render service and an app service

**Påbörjad:** 2026-08-30
**Senast uppdaterad:** 2026-08-30
**Status:** Fas 1–3 klara (PR 1 mergad, PR 2 ligger på gren); Fas 4 återstår

## Genomförda steg

### Fas 1 (PR 1 — mergad som #65)

- [x] Fas 1, steg 1: `render/` skapad som eget Python-projekt. `pyproject.toml` (`klartex-se-render` 0.1.0, `klartex==0.15.0` — samma pin som backend), `src/klartex_render/__init__.py`, `main.py` (FastAPI utan docs/openapi, `GET /health` med `status`/`version`/`klartex`, middleware som avvisar `Content-Length` över `MAX_REQUEST_BYTES` = 80 MB med 413 innan kroppen läses) och `render.py` (`RenderRequest` med `template`/`data`/`page_template_source`/`assets`, asset-validering mot samma `ASSET_NAME_RE` och samma gränser som registret, tempkatalog per anrop, `MAX_CONCURRENT_RENDERS = 2`, `_block_error_path` + `_BLOCK_ERROR_RE` och felmappningen flyttade hit ur `backend/src/klartex_se/render.py`).
- [x] Fas 1, steg 2: `render/tests/test_render.py` — 33 tester, alla gröna lokalt med xelatex på PATH.
- [x] Fas 1, steg 3: `render/Dockerfile` — samma `FROM ghcr.io/swedev/klartex-base`-pin (tagg + digest), `pip install .` ur `pyproject.toml`, `HEALTHCHECK` mot `/health`, `uvicorn klartex_render.main:app`.
- [x] Fas 1, steg 4: `render/README.md` — syfte, kontraktet, gränserna, felsvarstabellen, belastningstaket, lokal körning, deploy via `render-v*`.
- [x] Fas 1, steg 5: compose (tjänsten `render`, nätverket `render` med `internal: true`), `.env.example`, `deploy.yml` med `resolve`-jobbet och `render-v*`-triggern, `ci.yml` med matris och pin-kontroll.
- [x] Fas 1, steg 6: `infra/README.md` — två tjänster, två serier, GHCR-synlighet, säkerhet, felsökning.

### Fas 2 (PR 2)

- [x] Fas 2, steg 1: `backend/src/klartex_se/render_client.py` — `RENDER_URL` (default `http://render:8000`), `TIMEOUT` (connect 5 / write 30 / read 130), `RenderUpstreamError(status_code, detail, headers)`, `_client()` som modulfunktion så tester kan byta transport, och `render_pdf()`. Passthrough exakt enligt planen: 200 → bytes; {400, 500, 503} med ett `detail`-objekt som bär `type` och `message` (båda strängar) → samma status, samma `detail`, `Retry-After` vidare om den finns och inga andra headers; allt annat och varje `httpx.TransportError` → `502 render_unavailable` med generiskt meddelande och `log.warning` som bär status och början av kroppen.
- [x] Fas 2, steg 2: `backend/src/klartex_se/render.py` — kompilering, semafor-över-xelatex och felmappning borta. Kvar: tier-gaten, `find_latex_block`/`_child_block_lists`, sidmallsupplösningen. `MAX_INFLIGHT_RENDERS = 2` tas *före* bundle-laddningen; bundlens existens avgörs före semaforen, dess innehåll läses innanför. `RenderUpstreamError` → `HTTPException(status, detail, headers)`. `responses` dokumenterar 502 och beskriver 503 som antingen backends eller render-tjänstens.
- [x] Fas 2, steg 2b: `page_templates.load_bundle_payload(name) -> (source, assets)` — läser `page_template.tex.jinja` som UTF-8 och base64:ar varje asset i metadatans `asset_names`. Saknad bundle → `PageTemplateNotFound`; icke-UTF-8-källa, asset som saknas på disk eller ett assetnamn som inte matchar `ASSET_NAME_RE` → `PageTemplateError` (400 `input_error`).
- [x] Fas 2, steg 3: `backend/pyproject.toml` + `__init__.py` version 0.6.0; `httpx>=0.27` flyttad till huvudberoenden.
- [x] Fas 2, steg 4: `backend/Dockerfile` — `FROM python:3.12-slim`, `pip install .` ur `pyproject.toml`, healthcheck via `python -c "import urllib.request; …"`.
- [x] Fas 2, steg 5: tester. `test_render.py` omskriven mot `render_pdf` (bundle-payload, inbyggd sidmall i `data`, trasig bundle → 400, passthrough av 400/503 inklusive `Retry-After`, 502, in-flight-semaforen inklusive tredje samtidiga anrop, tier- och `find_latex_block`-testerna kvar). `test_render_client.py` (ny) kör `render_pdf` mot `httpx.MockTransport`: statusar, header-vidarebefordran, 422/HTML/ogiltig JSON/okänd status/trasigt `detail` → 502, fyra transportfel → 502, och tidsbudgeten pinnad. `test_contract.py` (ny) monkeypatchar `_client()` till `TestClient(klartex_render.main.app)` och kör kedjan i process: `validation_error` med `path`, blockfel med `path`, nästlat blockfel, okänd mall, "aldrig 422", asset-namn- och base64-validering, plus två xelatex-tester (minimal render, registrerad bundle med logotyp). `test_page_templates.py` har sju nya enhetstester för `load_bundle_payload`.
- [x] Fas 2, steg 6: `infra/docker-compose.yml` — `backend` får `RENDER_URL`, `depends_on: render: service_healthy`, python-healthchecken (compose-nivån åsidosätter imagens) och de slutgiltiga taken; `render` 1792m/1.5 CPU/256 pids, `backend` 768m/0.5 CPU/128 pids, summa 2560m som förut. Header-kommentaren beskriver budgeten i nu-state.
- [x] Fas 2, steg 7: `.github/workflows/deploy.yml` — backend-smoken kör en tvåcontainer-stack (den nybyggda imagen plus `klartex-se-render` på den version `.env.example` pinnar, på ett eget Docker-nätverk) och kontrollerar `/api/health`, `_block` i `/api/templates`, lika `klartex`-version i båda health-svaren, 403 för anonymt `latex`-block och en riktig PDF genom hela kedjan. Build-jobbet installerar `../render` när tjänsten är backend. På servern går render-kontrollen efter omstarten via `/api/render` för en backend-release och inifrån containern för en render-release, och en backend-deploy fallerar om tjänsternas `klartex`-versioner skiljer sig.
- [x] Fas 2, steg 8: `infra/Caddyfile` — `response_header_timeout` 180 s, med tidsbudgeten i kommentaren.
- [x] `.github/workflows/ci.yml`: install/test uppdelat, och backend-jobbet installerar `../render` för kontraktstestet.

### Fas 3 (i PR 2)

- [x] `backend/README.md` — rollen som policy-lager, `render_unavailable` i felsvarstabellen, belastningstaket delat mellan tjänsterna, tidsbudgeten, assets-avsnittet i nu-state, slim-Docker, `RENDER_URL` i lokal utveckling, `pip install -e ../render` för kontraktstestet. "Bumpa basimagen" är borta (den bor i `render/README.md`).
- [x] `infra/README.md` — tre containrar med `depends_on`, taggexemplen på 0.6-serien, deployens render-kontroll per tjänst, `klartex`-jämförelsen, resurstaken, 502-stycket och ett säkerhetsavsnitt i nu-state.
- [x] `PLAN.md` — beslutstabellens **API-image**- och **Hosting**-rader, **Bygge och deploy**-raden, risktabellens `/api/render`-rad.
- [x] `CLAUDE.md` — kärnprincip 1: backend är policy, `render/` är enda platsen som anropar `klartex.render()`.

## Pågående arbete

Inget. Fas 2–3 ligger komplett på `issue/46-split-backend-render-app-r2` och är avsedd som **PR 2**.

## Återstår

- **Fas 4** — utrullning:
  1. Tagga `render-v0.1.0` från `main` (PR 1 är mergad men taggen är inte satt). Verifiera i deploy-loggen att `render` är `healthy`, att dess interna render gav PDF och att `/api/render` fortfarande svarar.
  2. Mät två samtidiga renders mot `render` med `docker stats` innan PR 2 mergas — det avgör om 1792m i designbeslut 6 håller.
  3. Merga PR 2 → tagga `v0.6.0` → verifiera `/api/health` (0.6.0, samma `klartex` som `render`), render med inbyggd sidmall, med registrerad bundle och anonymt `latex`-block → 200/200/403.
  4. `docker compose exec render env` visar ingen `API_TOKEN`; `docker compose exec render curl -m 5 https://example.com` misslyckas.
  5. Uppdatera #19 med minnesmarginalen som förutsättning; PR 2 stänger #46 och #47.

## Anteckningar

- Designbeslut 8: PR 2 får inte mergas förrän `render-v0.1.0` ligger i produktion och minnesmätningen i Fas 4 steg 2 är gjord. Taggen är ännu inte satt, så den ordningen är inte uppfylld — grenen är klar att granskas, inte att merga.
- Verifieringschecklistans punkter som kräver `docker build`, en lokal compose-uppstart eller produktionsmiljön är inte körda här. Det som är kört: `pytest` i båda tjänsterna med och utan xelatex på PATH (106 respektive 33 gröna), `docker compose config` med och utan `RENDER_VERSION`, `bash -n` på workflowarnas run-block och YAML-parsning av båda workflowfilerna.
