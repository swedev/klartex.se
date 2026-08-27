# Plan: Issue #20 — Härda /render: rate limit, openin_any, och policy för latex-blocket

## Mål

Härda PDF-renderingen på `api.klartex.se` innan `/render` öppnas för anonyma anrop (#23). Efter issuekommentarens beslut 2026-08-27 återstår två av issuets fyra punkter här:

1. Grovt IP-baserat rate limit på `POST /render` i Caddy, plus storleksgräns på request-bodyn (issuets punkt 2).
2. Resurstak på backend-containern (minne, CPU, processer) plus tak på antal samtidiga renders (issuets punkt 4).

Utanför denna plan:

- **Issuets punkt 1 (`openin_any = p`) utgår** — användarbeslut i issuekommentaren 2026-08-27: TeX Live 2026 har tagit bort enforcementen av `openin_any` ur kpathsea, och prod kör redan TL2026. Filläsning under kompilering kan bara stängas med process-/OS-nivåisolering runt xelatex, vilket hör hemma i kärnan och blir ett eget issue där.
- **Issuets punkt 3 (`latex`-blocket kräver token)** implementeras enligt issuetexten tillsammans med #23.

## Triagering

> Beslutsunderlag för detta issue.

| Fält | Värde |
|------|-------|
| **Blockeras av** | Inget (punkterna är enligt issuet oberoende av åtkomstmodellen) |
| **Blockerar** | #23 (härdningen är en förutsättning för den anonyma nivån) |
| **Relaterade issues** | #23 (anonym nivå + finkornig kvot, tar även issuets punkt 3), #15 (API_TOKEN-auth; branch `issue/15-api-token-auth`, se konfliktnot) |
| **Omfattning** | ~12 filer i `backend/`, `infra/`, `deploy/`, `.github/workflows/` |
| **Risk** | Medel |
| **Komplexitet** | Medel |
| **Säker för junior** | Nej |
| **Konfliktrisk** | Medel — branchen `issue/15-api-token-auth` (öppen) överlappar i `backend/src/klartex_se/render.py`, `backend/tests/test_render.py`, `backend/pyproject.toml`, `backend/README.md`, `infra/docker-compose.yml` och `infra/.env.example` |

### Triagemässiga noteringar

- Verifierat i issuet mot produktion 2026-08-27: `POST /render` svarar 200 utan auth. Det är avsett beteende på `main` — härdningen ska inte vänta på auth-arbetet i #15/#23.
- **Issuets punkt 1 utgår — användarbeslut i issuekommentaren 2026-08-27.** TeX Live 2026 har tagit bort `openin_any`-enforcementen ur kpathsea (variabeln kan rapportera `p` utan att något enforcas), och prod är redan TL2026 (`Producer: xdvipdfmx (20260317)` verifierat mot `api.klartex.se`). Att pinna basimagen till TL2025 vore att flytta produktionen bakåt ett TeX Live-år. Filläsningsskyddet ersätts långsiktigt av process-/OS-nivåisolering i kärnan (eget kärn-issue). Konsekvens att bära med sig: tills dess kan `latex`-blockets råa källa läsa filer containern kommer åt, och endpointet är anonymt nåbart — ett argument för att #23 landar före en bredare lansering.
- **#17 har landat** (PR #24, merged till `main`): backend är `0.2.2` med klartex `0.14.0`. Ingen konflikt kvar därifrån.
- **Merge-ordning mot #15 måste väljas.** `git diff main...issue/15-api-token-auth` visar att #15 sätter `Depends(require_api_token)` på `render()`, väljer backend-version `0.3.0` och byter `ADMIN_TOKEN` → `API_TOKEN` i compose/`.env.example`. Rekommendation: **merga #20 först som `0.2.3`**, rebasa sedan #15 och jämka semafor + `Depends`, `responses`-dict, tester, compose-environment och version `0.3.0`. Landar #15 först gäller i stället: detta issue blir minst `0.3.1`, och render-smoketester/checklistor här måste skicka Bearer-token.
- Sekvens i övrigt: detta issue → #23.
- Kärnan kör redan `xelatex` med `-no-shell-escape` och 60 s timeout per körning, två körningar per render (`~/repos/klartex/klartex/renderer.py`, `_compile_tex`) — det som återstår för detta issue är resursförbrukning.
- Servern är en cax11: **2 vCPU, 4 GB RAM** (`infra/provision.sh`). Bekräfta gärna live med `hcloud server describe klartex-api-1` innan taken sätts.

## Angreppssätt

Två oberoende härdningar i två lager:

**1. Edge-lagret (Caddy rate limit + body-gräns).** Officiella `caddy:2-alpine` saknar rate limit-modul — `mholt/caddy-ratelimit` är en tredjepartsmodul som kräver en custom-byggd binär via `xcaddy`. En liten Caddy-image byggs på servern via compose (`build:`), så att arkitekturen (ARM) blir rätt automatiskt och ingen ny CI-pipeline behövs. Både Caddy-taggar och modulen version-pinnas. Zonen matchar `POST /render` per klient-IP (IPv6 aggregeras per /64 via `ipv6_prefix` så att adressrotation inom ett prefix inte kringgår taket); allt annat på API:t lämnas orört. 429 med `Retry-After` returneras vid överskriden kvot.

Dessutom sätts en storleksgräns på request-bodyn för `POST /render`: FastAPI läser och validerar hela JSON-bodyn **innan** semaforen i punkt 2 nås, så ett fåtal mycket stora requests kan äta backend-minne utan att uppta någon render-slot. En `request_body max_size` i Caddy tar bort den vektorn: Caddy kapar body-läsningen vid taket och svarar 413, så backend kan aldrig läsa in en komplett överstor body (proxyn kan ha börjat strömma bodyn till backend innan taket nås, men strömmen bryts där — FastAPI:s JSON-parse felar då i stället för att svälla). Gränsen gäller bara `/render` — `/page-templates`-uploads (bundles med fonter) kan legitimt vara större.

**2. Container-/processlagret (resurstak).** `docker-compose.yml` får `cpus`, `mem_limit`, `memswap_limit` och `pids_limit` på backend-tjänsten så att renderingar inte kan svälta Caddy och OS:et på cax11 (2 vCPU, **4 GB** RAM). Dessutom får `/render`-endpointen ett tak på samtidiga renders via en icke-blockerande semafor: FastAPI:s sync-endpoints körs i en trådpool med ~40 trådar, så utan tak kan 40 xelatex-processer startas parallellt — var och en inom containerns gräns men kollektivt förödande. Vid fullt hus svaras 503 + `Retry-After` direkt i stället för att köa obegränsat.

**Avgränsning — "per render" tolkas som aggregat, inte per-process-isolering.** Compose-taken gäller hela containern och semaforen begränsar bara samtidighet; en enskild render kan fortfarande nå containerns minnestak och OOM-döda pågående syskon-render. Äkta per-render-isolering (cgroups/ulimit per xelatex-process eller separat render-worker-container) kräver ändring i kärnan och tas inte här. Kombinationen 60 s×2-timeout per render (finns redan i kärnan) + max 2 samtidiga + containertak bedöms räcka för issuets mål "en tung men giltig payload ska inte lägga hela VM:en". Se designbeslut 3.

I samma veva rättas en timeout-obalans: Caddys `response_header_timeout` för API-proxyn är 60 s medan en render i värsta fall tar ~120 s (två xelatex-körningar à 60 s). Utan justering släpper Caddy anropet medan backend fortsätter uppta en semafor-slot.

## Steg

Ordningen är medveten: backend-taket först (rent Python, testbart lokalt utan infra), sedan Caddy-lagret, sist deploy-plumbingen mot den färdiga compose-konfigen.

### Fas 1: Resurstak

1. Tak på samtidiga renders i backend
   - `backend/src/klartex_se/render.py`: modulglobal `threading.BoundedSemaphore(2)`; i `render()` försök `acquire(blocking=False)` — vid misslyckande `HTTPException(503, detail={"type": "overloaded", ...}, headers={"Retry-After": "5"})`, annars rendera i `try/finally` med `release()` så sloten frigörs även när renderingen kastar.
   - Lägg `503: {"description": "Too many concurrent renders"}` i endpointens `responses`-dict.
   - Kodkommentar (teknisk constraint): gränsen förutsätter **en** uvicorn-worker per container — fler workers eller repliker multiplicerar taket.
   - Filer att ändra: `backend/src/klartex_se/render.py`
2. Tester för överlasttaket (körbara utan xelatex)
   - Fixture som ersätter/återställer den modulglobala semaforen per test, så ett fallerat test inte kontaminerar efterföljande.
   - 503-grenen: töm semaforen (två `acquire`), anrop ger 503 + `Retry-After`-header + `detail.type == "overloaded"`.
   - Slot-frigöring: mocka `klartex_render` att (a) lyckas och (b) kasta `RuntimeError` — efter bägge ska **båda** slottarna vara fria (två icke-blockerande `acquire` lyckas, ett tredje misslyckas); att bara ett efterföljande anrop går igenom bevisar inte att ingen slot läckt.
   - Samtidighet: mocka `klartex_render` med blockerande event + tre parallella requests (trådar/TestClient) — två väntar, tredje får omedelbar 503. Använd events/barriärer med bounded join-timeouts så testet inte kan hänga.
   - Filer att ändra: `backend/tests/test_render.py`
3. Kör limiter-testerna i CI före release
   - `.github/workflows/backend.yml` kör i dag bara smoketestet (en lyckad render), inte pytest. Lägg ett xelatex-fritt pytest-steg (checkout + `pip install -e '.[dev]'` + `pytest`) före image-pushen så limiter-regressioner fångas innan en tagg publiceras.
   - Filer att ändra: `.github/workflows/backend.yml`
4. Container-tak i compose
   - `backend`-tjänsten i `infra/docker-compose.yml`: `cpus: "1.5"`, `mem_limit: 2560m`, `memswap_limit: 2560m` (= inget swap-utnyttjande; en render som spränger taket ska dö snabbt, inte thrasha), `pids_limit: 256` (se designbeslut 3).
   - Filer att ändra: `infra/docker-compose.yml`
5. Bumpa backend-versionen — båda ställena
   - `version = "0.2.3"` i `backend/pyproject.toml` **och** `__version__ = "0.2.3"` i `backend/src/klartex_se/__init__.py` (annars säger image-taggen 0.2.3 medan `/health`/OpenAPI rapporterar 0.2.2). Main är `0.2.2` sedan #17/PR #24; förutsätter att #20 landar före #15 — se triagenoteringen om merge-ordning; annars minst `0.3.1`.
   - Filer att ändra: `backend/pyproject.toml`, `backend/src/klartex_se/__init__.py`
6. Dokumentera driftbeteendet
   - `backend/README.md`: notera 503-beteendet vid fullt hus (`Retry-After`) och single-worker-förutsättningen för taket; rätta samtidigt den felaktiga variabelreferensen `KLARTEX_SE_BACKEND_VERSION` → `BACKEND_VERSION` (rad 71).
   - Filer att ändra: `backend/README.md`

### Fas 2: Rate limit + body-gräns på `POST /render` i Caddy

1. Custom Caddy-image med rate limit-modulen, version-pinnad
   - Första åtgärd: slå upp aktuell stabil Caddy-version och senaste tagg/commit för `mholt/caddy-ratelimit`, och skriv in de konkreta värdena — inga platshållare i den implementerade filen.
   - Ny fil `infra/caddy/Dockerfile`:
     - Steg 1: `caddy:<version>-builder` + `xcaddy build --with github.com/mholt/caddy-ratelimit@<pinnad-tag-eller-commit>`
     - Steg 2: `caddy:<version>-alpine`, `COPY --from=builder /usr/bin/caddy /usr/bin/caddy`
     - Builder- och runtime-taggen ska vara **samma exakta version**; modulen är tredjeparts och opinnad `latest` gör bygget o-reproducerbart.
   - Filer att skapa: `infra/caddy/Dockerfile`
2. Byt compose-tjänsten till den byggda imagen
   - `caddy`-tjänsten i `infra/docker-compose.yml`: ersätt `image: caddy:2-alpine` med `build: ./caddy` + `image: klartex-se-caddy:local` (lokalt namn, aldrig pushad).
   - Filer att ändra: `infra/docker-compose.yml`
3. Rate limit, body-gräns och timeout-justering i Caddyfile
   - I `api.klartex.se`-blocket, i denna stil (exakt syntax verifieras mot [modulens README](https://github.com/mholt/caddy-ratelimit) vid implementation):
     ```caddyfile
     @render {
         method POST
         path /render
     }
     request_body @render {
         max_size 2MB
     }
     rate_limit {
         zone render_per_ip {
             match {
                 method POST
                 path /render
             }
             key         {client_ip}
             events      10
             window      1m
             ipv6_prefix 64
         }
     }
     ```
   - `max_size 2MB` är väl tilltaget för `/render`-payloads — `RenderRequest` bär bara JSON-dokumentdata och ett page-template-namn, inga inline-assets, så även stora dokument ligger långt under gränsen (stickprova gärna representativa payloads före låsning). För stor body kapas vid taket och ger 413. Gränsen gäller inte `/page-templates`.
   - Caddy sitter direkt mot internet, så `{client_ip}` är riktig klient-IP utan trusted_proxies-konfiguration.
   - Höj `response_header_timeout` i `reverse_proxy`-transporten från 60 s till 150 s — värsta legitima render är ~120 s (två xelatex-körningar à 60 s) och Caddy ska inte överge anrop som backend fortfarande arbetar med.
   - Övriga endpoints (`GET /templates`, `/blocks`, `/page-templates`, `/health`) lämnas utan limit.
   - Filer att ändra: `infra/Caddyfile`
4. Bygg, preflight-validera och skydda rollback-vägen vid deploy
   - `deploy/deploy.sh`:
     - **Nytt SSH-steg före rsyncen** (deploy.sh:s remote-block körs i dag efter rsync — backupen måste vara ett eget steg innan): säkerhetskopiera körande konfig till en katalog **utanför** `/srv/klartex` (t.ex. `cp /srv/klartex/{docker-compose.yml,Caddyfile,.env} /srv/klartex-deploy-backup/` + `cp -r /srv/klartex/caddy /srv/klartex-deploy-backup/` om den finns). Inuti `/srv/klartex` duger inte: rsyncen kör `--delete` och skulle radera en backup-katalog som inte finns lokalt. Utan backup skriver rsyncen över live-konfigen innan den validerats, och en reboot mitt i skulle starta stacken på ovaliderade filer.
     - I remote-blocket: byt `docker compose pull` → `docker compose pull --ignore-buildable` (compose försöker annars pulla `klartex-se-caddy:local` som inte finns i något registry; verifiera att serverns compose-version stödjer flaggan — den finns i modern Compose v2).
     - `docker compose build --pull caddy` (unitens `docker compose up -d` bygger inte om vid Dockerfile-ändring). Serverkrav att notera i README: utgående åtkomst till Docker Hub/GitHub/Go-moduler och tillräckligt disk/RAM för xcaddy-kompileringen.
     - Preflight innan restart: `docker compose run --rm --no-deps caddy caddy list-modules | grep rate_limit` (modulen finns i binären) och `docker compose run --rm --no-deps caddy caddy validate --config /etc/caddy/Caddyfile` (konfigen parsas). Faller bygget, preflighten eller stackstarten (compose ps/health efter restart): återställ backupen till `/srv/klartex/` och restarta stacken på den — gamla stacken rullar vidare på giltiga filer; avbryt deployen med fel.
   - Rollback om nya Caddy trots preflight inte startar: återställ `image: caddy:2-alpine` (ta bort `build:`) + föregående Caddyfile i git, kör `deploy.sh` igen; certifikaten ligger kvar i `./caddy-data` och påverkas inte.
   - Filer att ändra: `deploy/deploy.sh`
5. Dokumentera
   - `infra/README.md`: rad för `caddy/Dockerfile` i "Vad ligger var", notis om att Caddy byggs på servern (varför: tredjepartsmodul + rätt ARM-arch utan CI-pipeline), server-byggkraven ovan, och hur versionerna bumpar. Rätta samtidigt de inaktuella `KLARTEX_VERSION`-referenserna till `BACKEND_VERSION` (rad 13, 29, 37, 41).
   - Filer att ändra: `infra/README.md`

### Fas 3: Release och driftsättning

1. Merge till `main` → `.github/workflows/backend.yml` kör pytest (nya steget från fas 1), bygger, kör smoketestet och pushar `ghcr.io/swedev/klartex-se-backend:0.2.3`.
2. Bumpa `BACKEND_VERSION=0.2.3` i **lokala** `infra/.env` (gitignorerad; deploy.sh kräver den lokalt och rsyncar den till servern — en ren server-side-redigering skrivs över vid nästa deploy). Uppdatera exempelvärdet i `infra/.env.example` (står i dag på `0.2.0`).
   - Filer att ändra: `infra/.env.example` (+ lokala `infra/.env`, ej i git)
3. Kör `./deploy/deploy.sh` — backupar serverkonfig, rsyncar infra (nya Caddyfile + caddy/Dockerfile + compose), bygger + preflight-validerar Caddy, pullar backend, restartar stacken.
4. Kör verifieringschecklistan nedan mot produktion — i checklistans ordning: rate limit-testet sist, eftersom det tömmer käll-IP:ns kvot och annars ger 429 på efterföljande tester.
5. Koordineringsöverlämning (ingår inte i #20:s implementation): rebasa `issue/15-api-token-auth` mot nya `main` och jämka (semafor + `Depends`, `responses`-dict, tester, compose-env, version `0.3.0`) — eller, om #15 redan landat, ha redan anpassat denna plan enligt triagenoteringen.

## Filöversikt

| Fil | Åtgärd | Syfte |
|-----|--------|-------|
| `backend/pyproject.toml` | Ändra | Versionsbump 0.2.2 → 0.2.3 |
| `backend/src/klartex_se/__init__.py` | Ändra | Samma versionsbump (`__version__` driver `/health`/OpenAPI) |
| `backend/src/klartex_se/render.py` | Ändra | Icke-blockerande semafor: max 2 samtidiga renders, annars 503; `responses`-dict |
| `backend/tests/test_render.py` | Ändra | Tester: 503-gren, full slot-återställning vid lyckad/misslyckad render, samtidighet |
| `backend/README.md` | Ändra | Dokumentera 503/`Retry-After` + single-worker-constraint; rätta `KLARTEX_SE_BACKEND_VERSION` → `BACKEND_VERSION` |
| `.github/workflows/backend.yml` | Ändra | Nytt xelatex-fritt pytest-steg före image-push |
| `infra/caddy/Dockerfile` | Skapa | Pinnat xcaddy-bygge med `mholt/caddy-ratelimit` |
| `infra/docker-compose.yml` | Ändra | Caddy `build:`; backend `cpus`/`mem_limit`/`memswap_limit`/`pids_limit` |
| `infra/Caddyfile` | Ändra | `rate_limit`-zon (`ipv6_prefix 64`); `request_body max_size` för `/render`; `response_header_timeout` 60 s → 150 s |
| `deploy/deploy.sh` | Ändra | Konfig-backup utanför `/srv/klartex` före rsync; `pull --ignore-buildable`; `build --pull caddy`; preflight `list-modules` + `validate` med återställning vid fel |
| `infra/README.md` | Ändra | Dokumentera server-byggd Caddy-image + byggkrav; rätta `KLARTEX_VERSION` → `BACKEND_VERSION` |
| `infra/.env.example` | Ändra | Exempelversion 0.2.3 |

## Berörda kodområden

Lista de primära kataloger/områden som planen berör (för konfliktdetektering):
- `backend/` (`src/klartex_se/render.py`, `__init__.py`, tester, pyproject, README)
- `infra/` (Caddyfile, docker-compose.yml, ny `caddy/`-katalog)
- `deploy/` (deploy.sh)
- `.github/workflows/` (backend.yml)

## Designbeslut

> Icke-triviala val gjorda under planeringen. Feedback välkommen; annars implementeras enligt dessa.

### 1. Caddy-imagen byggs på servern via compose, inte i CI
**Alternativ:** (A) `build:` i compose + `docker compose build` i deploy.sh vs (B) ny GitHub-workflow som pushar en custom Caddy-image till GHCR.
**Beslut:** A, med pinnade Caddy-taggar och pinnad modulversion + preflight (`list-modules`, `validate`) och konfig-backup i deploy.sh.
**Motivering:** Ett enda plugin motiverar ingen ny CI-pipeline och image att versionera; server-bygget ger automatiskt rätt arkitektur (ARM) och deploy-flödet äger redan rsync av `infra/`. Bygget tar någon minut och sker sällan (bara när caddy/Dockerfile ändras — Docker cachear annars). Pinning + preflight + backup tar bort riskerna med server-byggen: o-reproducerbarhet, att en trasig binär upptäcks först efter att gamla stacken stoppats, och att ovaliderad konfig ligger kvar på disk vid avbruten deploy. *Proveniens: agentens egen bedömning — öppen att ifrågasätta; issuet säger bara "i Caddy".*

### 2. Rate limit-nivå: 10 renders/minut per IP (IPv6: per /64), ingen global zon, body-tak 2 MB
**Alternativ:** stramare (t.ex. 3/min) vs generösare (t.ex. 30/min); med/utan en global zon utöver per-IP; body-gräns i Caddy vs i FastAPI.
**Beslut:** `events 10`, `window 1m`, nycklad på klient-IP med `ipv6_prefix 64`, endast `POST /render`. Ingen global zon i denna omgång. `request_body max_size 2MB` på samma matcher.
**Motivering:** Detta är det *grova* taket — issuet lägger finkornig kvot per nivå i #23. 10/min stoppar CPU-stöld via loop utan att störa en legitim användare som itererar på ett dokument. Body-gränsen ligger i Caddy eftersom FastAPI redan hunnit läsa in bodyn i minnet när applikationskod kan reagera. Medvetet accepterad lucka: distribuerade klienter (många IP:n) kan tillsammans hålla båda render-slottarna upptagna och svälta legitima användare — semaforen skyddar då värdens hälsa men inte rättvisan. En global zon skulle mildra det men ger också en trivial DoS-spak mot alla; den avvägningen hör hemma i #23:s nivåmodell. *Proveniens: agentens egen bedömning — siffrorna är startpunkter och lätta att justera i Caddyfile; svältluckan är ett öppet val att ompröva.*

### 3. Container-tak: `cpus: 1.5`, `mem_limit: 2560m`, `memswap_limit: 2560m`, `pids_limit: 256`
**Alternativ:** hårdare tak (1 CPU / 2 GB) vs inga compose-tak alls (lita på semaforen).
**Beslut:** 1,5 av 2 vCPU, 2,5 av 4 GB, inget swap, 256 pids.
**Motivering:** cax11 har **4 GB** RAM (`infra/provision.sh`); OS + Caddy + Docker behöver garanterad marginal (~1,5 GB) även när backend är mättad. 1,5 vCPU låter två renders fortfarande gå snabbt. `memswap_limit = mem_limit` gör att en render som spränger taket OOM-dödas direkt i stället för att thrasha disken. `pids_limit` stoppar fork-svärmar oavsett orsak. Compose-taket är skyddet som håller även om applikationslagret fallerar. Bekräfta serverstorleken live (`hcloud server describe`) innan värdena låses. *Proveniens: agentens egen bedömning utifrån cax11:s specifikation (2 vCPU, 4 GB) — öppen att ifrågasätta.*

### 4. Applikationsnivå-tak: max 2 samtidiga renders, 503 i stället för kö; "per render" = aggregat
**Alternativ:** (A) icke-blockerande semafor → omedelbar 503, (B) blockerande kö med väntetid, (C) inget app-tak (bara container-tak), (D) äkta per-render-isolering (cgroup/ulimit per xelatex eller render-worker-container).
**Beslut:** A, gräns 2 (= antal vCPU). D tas inte i detta issue.
**Motivering:** C räcker inte: FastAPI kör sync-endpoints i en trådpool (~40 trådar), så 40 parallella xelatex-processer kan starta — var och en inom containergränsen men kollektivt sväller de tills OOM-killern tar containern, vilket fäller *alla* pågående renders. B binder trådar och göder retry-stormar. D kräver ändring i kärnan (subprocess-limits i `_compile_tex`) eller en worker-arkitektur — fel skala för detta issue; kombinationen render-timeout (60 s×2, finns redan) + samtidighetstak + containertak uppfyller issuets mål att en tung payload inte lägger VM:en, men en enskild render kan fortfarande OOM-döda containern och därmed sin syskon-render. *Proveniens: agentens egen bedömning — issuets punkt 4 säger "minne och CPU per render"; planens aggregat-tolkning och avfärdandet av D lyfts här som öppen fråga. Behövs äkta per-render-isolering blir det ett kärn-issue.*

### 5. Issuets punkt 1 (`openin_any = p`) utgår; sandboxing blir ett kärn-issue
**Alternativ:** (A) pinna basimagen till TeX Live 2025 där `openin_any` fortfarande enforcas, (B) stanna på `latest` (TL2026) och ersätta skyddet med process-/OS-nivåisolering nu, (C) släppa punkten ur detta issue och lägga sandboxing som eget kärn-issue.
**Beslut:** C.
**Motivering:** TeX Live 2026 har [tagit bort `openin_any`-enforcementen](https://tug.org/texlive/bugs.html) ur kpathsea — konfigvärdet kan rapportera `p` utan att något enforcas. Prod kör redan TL2026, så A vore att flytta produktionen bakåt ett TeX Live-år, samtidigt som kärnan bumpats till 0.14.0 (#17). B (sanerad process-env, bwrap/cgroups per xelatex) är rätt långsiktigt men kräver ändringar i kärnans `_compile_tex` och är fel skala för detta issue. Kvarstående exponering: `latex`-blockets råa källa kan läsa filer containern kommer åt tills sandboxing finns — därför bör #23 (som tar `latex`-blocket ur den anonyma nivån) landa före en bredare lansering. *Proveniens: användarbeslut i issuekommentaren 2026-08-27 ("Beslut: punkt 1 utgår ur det här issuet").*

### 6. Issuets punkt 3 (`latex`-blocket kräver token) görs i #23
**Alternativ:** ta med den här vs lämna till #23.
**Beslut:** Lämnas till #23.
**Motivering:** Issuetexten säger uttryckligen att punkt 3 implementeras tillsammans med #23, eftersom den förutsätter nivåmodellen (anonym vs token). *Proveniens: användarbeslut i issue #20.*

## Verifieringschecklista

Ordningen är medveten: rate limit-testet ligger sist eftersom det tömmer käll-IP:ns kvot för en minut.

- [ ] `pytest` i `backend/` grönt: 503-gren, slot-frigöring efter lyckad + misslyckad render, samtidighetstest (allt utan xelatex).
- [ ] CI-smoketestet (minimal `_block`-render → 200 + `%PDF`) passerar oförändrat med semaforen på plats.
- [ ] Caddy-imagen bygger på ARM; preflight `caddy list-modules` visar `rate_limit`; `caddy validate` accepterar nya Caddyfile — allt innan gamla stacken stoppas.
- [ ] Efter deploy: `docker inspect klartex-se-backend` visar CPU-/minnes-/swap-/pids-gränserna.
- [ ] Tre samtidiga renders: två går igenom, tredje får omedelbar 503 med `Retry-After`.
- [ ] Lång render (~>60 s) fullföljer genom Caddy utan att proxyn ger upp (`response_header_timeout` 150 s).
- [ ] `POST /render` med body > 2 MB ger 413 från Caddy utan att nå backend.
- [ ] Produktionsverifieringen från issuet upprepad: rendering fungerar end-to-end (vkf-bundlen) efter härdningarna.
- [ ] Sist, efter minst en hel tyst window (60 s utan `POST /render` från käll-IP:n — tidigare checklistesteg har annars redan fyllt hinken): 11 billiga (ogiltiga, t.ex. tomt `data` → 400) `POST /render` inom en minut från samma IP → nr 11 ger 429 + `Retry-After`; `GET /templates` och `/health` opåverkade. (Rate limit-matchning sker i Caddy på metod+path, före backend, så 400-svar räknas mot kvoten.)
- [ ] I samma test: ett anrop med spoofad `X-Forwarded-For` räknas fortfarande mot käll-IP:ns hink (Caddy utan `trusted_proxies` litar inte på headern) — headern får inte vara en bypass.
