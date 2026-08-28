# Plan: Issue #32 — CI: stop rebuilding the 7 GB TeX Live image on every release

## Mål

Sluta bygga om den ~7 GB stora TeX Live-imagen vid varje release. De tunga, sällan ändrade lagren (TeX Live, mscorefonts, apt-paket, texlive-bin-symlänken) bryts ut till en basimage `ghcr.io/swedev/klartex-se-base` med egen workflow, och app-Dockerfilen blir `FROM <basimage>` plus venv-install och `COPY src/`. Samtidigt fixas lager-invalideringen: `COPY pyproject.toml ./` före pip-installen används inte och tas bort, så en versionsbump bara invaliderar `COPY src/`-lagret. En release-build går då från ~15 minuter till ett par minuter, oberoende av GHA-cachens eviction.

## Triagering

> Beslutsunderlag för detta issue.

| Fält | Värde |
|------|-------|
| **Blockeras av** | Inget |
| **Blockerar** | Inget |
| **Relaterade issues** | Inga direkt; #20 (öppen) har en plan som också rör `.github/workflows/backend.yml` |
| **Omfattning** | 7 filer i `backend/`, `.github/workflows/` och repo-roten (2 nya, 5 ändrade — varav 2 rena dok-/kommentarsuppdateringar) |
| **Risk** | Medel |
| **Komplexitet** | Medel |
| **Säker för junior** | Nej |
| **Konfliktrisk** | Låg — plan #20 rör `.github/workflows/backend.yml`, men dess ändring där (pytest-steg före image-push) finns redan på `main`; plan #17 rörde `backend/Dockerfile` men issue #17 är stängt |

### Triagemässiga noteringar

Inga blockerande issues. Utrullningen är en **tvåstegs-utrullning** (två PR:er) eftersom basimagen måste finnas i GHCR innan app-Dockerfilen som pekar på den kan byggas — se designbeslut 2. **Fas 1 är klar:** PR #35 mergades 2026-08-28 och basworkflown publicerade `ghcr.io/swedev/klartex-se-base:20260828-1` (amd64 + arm64). Återstår fas 2. `deploy.yml` behöver inga logikändringar (verifierat: den verifierar bara att imagen finns i GHCR och rullar ut den; den bygger aldrig) — bara en stale kommentar rättas.

Operativa förutsättningar:
- GHCR-paketet `klartex-se-base` är skapat och **publikt** (samma synlighet som `klartex-se-backend`) — gaten för fas 2 är uppfylld; lokala byggen av app-imagen fungerar utan ghcr-login.
- Publicerade bastaggar som refereras av någon app-Dockerfile i historiken får inte raderas — då går de byggena inte att reproducera.

## Angreppssätt

Två samverkande problem gör att varje release bygger om allt:

1. **GHA-cachen räcker inte.** `type=gha` delar repots cache-utrymme (10 GB är default-gränsen, och den som gäller här). TeX Live-lagren (~7 GB × 2 arkitekturer, `mode=max`) evictas nästan direkt, så det QEMU-emulerade arm64-bygget körs om i sin helhet (~15 min) för ett byte-identiskt resultat. En höjd cachegräns vore ett plåster — basimage-splitten tar bort cache-beroendet helt och är dessutom deterministisk.
2. **Onödig lager-invalidering.** `backend/Dockerfile` har `COPY pyproject.toml ./` före `pip install`-lagret, men install-steget läser aldrig filen (den installerar en explicit pinnad lista). Varje versionsbump i `pyproject.toml` invaliderar därför venv-lagret i onödan — även en perfekt cache hade inte hjälpt där.

Lösningen tar bort cache-beroendet i stället för att slåss mot det: de tunga lagren flyttas till `backend/Dockerfile.base`, publicerad som `ghcr.io/swedev/klartex-se-base` av en egen workflow som bara triggar när den filen (eller dess workflow) ändras — i praktiken några gånger om året. App-bygget hämtar basimagen som färdiga lager från GHCR (ingen cache-tur inblandad) och bygger bara venv + `COPY src/` — någon minut även under QEMU.

Basimagen pinnas explicit i app-Dockerfilens `FROM`-rad (tagg + manifest-digest), så app-byggen är reproducerbara och en basbump är en explicit, granskningsbar ändring.

`backend.yml` behåller sitt flöde (tester → amd64-smoke-test → multi-arch-push) mot den slimmade Dockerfilen. Smoke-testet renderar genom hela stacken och fångar därmed fortfarande saknade TeX-paket, även när felet skulle ligga i basimagen.

## Steg

### Fas 1: Basimage och basworkflow (PR 1 — klar, mergad som #35)

1. Skapa `backend/Dockerfile.base` med de tunga, sällan ändrade lagren, flyttade oförändrade från nuvarande `backend/Dockerfile` (inklusive kommentarerna som förklarar dem):
   - `FROM texlive/texlive:latest`
   - apt-lagret: `python3 python3-pip python3-venv curl`
   - mscorefonts-lagret (contrib-källa, debconf-EULA, `fc-cache`)
   - `RUN ln -s ... /usr/local/texlive-bin`-symlänken
   - Avslutande sanity-check-lager som kör per plattform vid bygget och felar bygget om basen är trasig, t.ex. `RUN /usr/local/texlive-bin/xelatex --version && /usr/local/texlive-bin/kpsewhich fontspec.sty && fc-list | grep -qi georgia && fc-list | grep -qi arial` — fångar trasig symlänk, saknad TeX-installation och misslyckad fontinstallation redan i basbygget (på båda arkitekturerna, till skillnad från app-smoke-testet som bara kör amd64). Obs: TeX-binärerna ligger inte i `PATH` i basen (ingen `ENV` där), så checken måste använda symlänkens absoluta sökväg
   - Ingen `WORKDIR`, `ENV`, `EXPOSE`, `HEALTHCHECK` eller `CMD` — basen är ett rent lager-underlag; runtime-konfigurationen stannar i app-Dockerfilen (se designbeslut 4)
   - Filer att ändra: `backend/Dockerfile.base` (ny)
2. Skapa `.github/workflows/backend-base.yml`:
   - Triggers: `push` mot `main` med `paths: ['backend/Dockerfile.base', '.github/workflows/backend-base.yml']`, samt `workflow_dispatch` med valfri `tag`-input (för override)
   - `permissions: contents: read, packages: write`
   - Steg: checkout → `docker/setup-qemu-action@v3` → `docker/setup-buildx-action@v3` → `docker/login-action@v3` mot ghcr → beräkna tagg `$(date -u +%Y%m%d)-${{ github.run_number }}` (input-övertrumfar) → `docker/build-push-action@v6` med `context: ./backend`, `file: ./backend/Dockerfile.base`, `platforms: linux/amd64,linux/arm64`, `push: true`, tagg `ghcr.io/swedev/klartex-se-base:<tagg>`
   - Ingen `latest`-tagg och ingen GHA-cache (se designbeslut 1 och 3)
   - Filer att ändra: `.github/workflows/backend-base.yml` (ny)
3. Lägg till `- '!backend/Dockerfile.base'` i `paths`-filtret i `.github/workflows/backend.yml` redan i denna PR, så att framtida bas-ändringar inte triggar meningslösa app-byggen. Obs: PR 1-mergen i sig triggar ändå ett sista fullbygge av app-imagen — PR:en ändrar `.github/workflows/backend.yml`, som är en egen positiv path-match. Det är förväntat och ofarligt (bygger nuvarande Dockerfile som förut)
   - Filer att ändra: `.github/workflows/backend.yml`
4. Efter merge av PR 1 — genomfört, med resultat:
   - Basworkflown körde grönt på merge-committen; `docker buildx imagetools inspect` bekräftar att `ghcr.io/swedev/klartex-se-base:20260828-1` finns med både `linux/amd64` och `linux/arm64`
   - Paketet `klartex-se-base` är **publikt** i GHCR (samma synlighet som `klartex-se-backend`)
   - Pinne för fas 2: tagg `20260828-1`, manifest-digest `sha256:640992b132b9880eb0f801b81ac5f30ea64190243fa8900fbfda098cb158562b`

### Fas 2: Slimmad app-Dockerfile och workflow-justering (PR 2)

1. Skriv om `backend/Dockerfile`:
   - `FROM ghcr.io/swedev/klartex-se-base:20260828-1@sha256:640992b132b9880eb0f801b81ac5f30ea64190243fa8900fbfda098cb158562b` — tagg för läsbarhet, digest för äkta immutabilitet (publicerad i fas 1)
   - Ta bort de lager som flyttat till basen
   - Ta bort `COPY pyproject.toml ./` (används inte av install-steget)
   - Behåll: `WORKDIR /app`, venv-skapande + pip-install av den pinnade listan, `COPY src/ ./src/`, `ENV PATH/PYTHONPATH/PYTHONUNBUFFERED`, `EXPOSE`, `HEALTHCHECK`, `CMD`
   - Uppdatera huvudkommentaren så den beskriver bas-upplägget (var de tunga lagren bor, hur man bumpar)
   - Filer att ändra: `backend/Dockerfile`
2. Verifiera lokalt före merge: `docker build` av den omskrivna app-Dockerfilen (drar basen från GHCR), starta containern och kör render-anropet ur smoke-testet — `backend.yml` kör bara på push till `main`, så detta är enda verifieringen före merge. (Skyddsnätet vid miss: `backend.yml` pushar aldrig en image förrän amd64-smoke-testet passerat, så en trasig bas ger en röd CI-körning, inte en trasig release.)
3. Uppdatera `backend/README.md` (sektionerna **Docker** och **Deploy**):
   - Beskriv tvådelningen: basimage (`Dockerfile.base` → `ghcr.io/swedev/klartex-se-base`, byggd av `backend-base.yml`) + app-image
   - Dokumentera bump-proceduren för basen: ändra `Dockerfile.base` → merge (basworkflown publicerar ny tagg) → separat PR som bumpar `FROM`-pinnen i `Dockerfile`
   - Notera att lokala `docker build` av app-imagen drar basen från GHCR, samt att publicerade bastaggar inte får raderas så länge de refereras
   - Filer att ändra: `backend/README.md`
4. Uppdatera stale dokumentation som beskriver det gamla upplägget:
   - `PLAN.md`, raden **API-image** i "Tagna beslut": basera beskrivningen på `klartex-se-base` + slim app-image i stället för "`texlive/texlive:latest`-bas + mscorefonts"
   - `.github/workflows/deploy.yml`, huvudkommentaren: "Rebuilding here would repeat a ~15 minute arm64 build" stämmer inte längre — skriv om motiveringen (bygget hör hemma i `backend.yml`; deploy rullar bara ut en redan smoke-testad image). Ingen logikändring.
   - Filer att ändra: `PLAN.md`, `.github/workflows/deploy.yml`
5. Verifiera efter merge av PR 2 att release-bygget (`backend.yml`) går på ett par minuter och att smoke-testet passerar

## Filöversikt

| Fil | Åtgärd | Syfte |
|-----|--------|-------|
| `backend/Dockerfile.base` | Skapa (PR 1 — klar) | Tunga, sällan ändrade lager: TeX Live-bas, apt-paket, mscorefonts, texlive-bin-symlänk, sanity-check |
| `.github/workflows/backend-base.yml` | Skapa (PR 1 — klar) | Bygger + pushar multi-arch basimage till `ghcr.io/swedev/klartex-se-base`; triggar bara på basfilens/egna workflowns ändringar |
| `.github/workflows/backend.yml` | Ändra (PR 1 — klar) | Exkludera `Dockerfile.base` ur `paths`-filtret; i övrigt oförändrat flöde |
| `backend/Dockerfile` | Ändra (PR 2) | `FROM` pinnad basimage; ta bort flyttade lager och oanvänd `COPY pyproject.toml` |
| `backend/README.md` | Ändra (PR 2) | Dokumentera bas-/app-uppdelningen och bump-proceduren |
| `PLAN.md` | Ändra (PR 2) | Uppdatera stale **API-image**-raden i "Tagna beslut" |
| `.github/workflows/deploy.yml` | Ändra (PR 2) | Endast kommentar: motiveringen "rebuild tar ~15 min" stämmer inte längre |

## Berörda kodområden

Lista de primära kataloger/områden som planen berör (för konfliktdetektering):
- `backend/` (endast Dockerfile/README — ingen Python-kod)
- `.github/workflows/`

## Designbeslut

> Icke-triviala val gjorda under planeringen. Feedback välkommen; annars implementeras enligt dessa.

### 1. Immutabel datumtagg (`YYYYMMDD-<run_number>`) för basimagen, ingen `latest`
**Alternativ:** ren datumtagg (`YYYYMMDD`) vs content-hash av `Dockerfile.base` vs datum + run-nummer
**Beslut:** `YYYYMMDD-<github.run_number>` som tagg, och app-Dockerfilen pinnar dessutom manifest-digesten (`<tagg>@sha256:<digest>`). Ingen `latest`-tagg publiceras.
**Motivering:** Basen bygger från `texlive/texlive:latest`, så samma Dockerfile-innehåll ger olika imageinnehåll vid olika byggen — en content-hash-tagg skulle tyst skrivas över med nytt innehåll vid en omkörning, och en ren datumtagg har samma problem vid omkörning samma dag. Run-numret gör taggen unik per körning, men inte per *försök* (`run_number` ändras inte vid re-run, och dispatch-inputen kan återanvända en befintlig tagg) — därför pinnar app-Dockerfilen digesten, som är immutabel på riktigt oavsett vad som händer med taggen. Taggen ger läsbarhet och rollback är trivialt (bumpa tillbaka `FROM`-pinnen); basbumpen är explicit i diffen. `latest` utelämnas helt — ingen konsument ska någonsin peka på en rörlig referens, och då ska den inte finnas att peka på. Issuet lämnar valet öppet ("date or content-hash tag"); detta är agentens egen bedömning och öppen att ifrågasätta.

### 2. Två PR:er — basen först, sedan den slimmade app-Dockerfilen
**Alternativ:** allt i en PR vs bas-PR följt av app-PR
**Beslut:** Två PR:er.
**Motivering:** App-Dockerfilen måste pinna en tagg som redan finns i GHCR; i en enda PR skulle `backend.yml` trigga på merge och fela innan basworkflown hunnit publicera (och datumtaggen är dessutom okänd tills bygget körts). Två PR:er ger noll trasiga CI-körningar och etablerar samtidigt den stående bump-proceduren för framtida basändringar. Agentens egen bedömning (issuet specificerar inte utrullningsordning).

### 3. Ingen GHA-cache i basworkflown
**Alternativ:** `type=gha`-cache även för basbygget vs ingen cache
**Beslut:** Ingen cache.
**Motivering:** 10 GB-gränsen och evictionen är själva grundproblemet — ~7 GB × 2 arkitekturer ryms aldrig, och cache-stegen kostar bara uppladdningstid. Basbygget körs några gånger per år och får ta sina ~15–20 min under QEMU. Agentens egen bedömning.

### 4. Runtime-konfigurationen stannar i app-Dockerfilen
**Alternativ:** flytta `ENV PATH` m.m. till basen vs behålla allt i app-Dockerfilen
**Beslut:** Behåll `WORKDIR`, `ENV`, `EXPOSE`, `HEALTHCHECK`, `CMD` i app-Dockerfilen.
**Motivering:** `PATH` refererar både `/usr/local/texlive-bin` (bas) och `/opt/venv/bin` (app); att dela upp den över två filer gör helheten svårare att läsa utan att spara något. Basen förblir ett rent lager-underlag. Agentens egen bedömning.

## Verifieringschecklista

- [x] `backend-base.yml` bygger och pushar `ghcr.io/swedev/klartex-se-base` (amd64 + arm64) — och triggar *inte* på vanliga `backend/**`-ändringar (`paths`-filtret listar bara `Dockerfile.base` och workflown själv); verifierat med `imagetools inspect` av `20260828-1`
- [x] Sanity-check-lagret i `Dockerfile.base` kör och passerar på båda plattformarna (xelatex, fontspec, Georgia/Arial) — basbygget gick grönt på båda arkitekturerna
- [x] GHCR-paketet `klartex-se-base` har samma synlighet som `klartex-se-backend` (båda publika)
- [x] `backend/Dockerfile` pinnar basimagen med tagg **och** manifest-digest (`<tagg>@sha256:<digest>`) — aldrig en rörlig referens; digesten kontrollerad mot GHCR-manifestet för `20260828-1`
- [ ] Lager-invalidering verifierad kontrollerat: två lokala byggen med samma cache där enbart `backend/pyproject.toml` ändrats emellan visar `CACHED` på venv-`RUN`-steget (vid en riktig release ändras även `src/`, så `COPY src/` är då första invaliderade lagret)
- [ ] Release-bygget i `backend.yml` går på ett par minuter i stället för ~15
- [ ] Smoke-testet renderar en PDF genom hela stacken (fångar saknade TeX-paket även från basen)
- [ ] En ändring i enbart `backend/Dockerfile.base` triggar basworkflown men inte `backend.yml`
- [x] `deploy.yml` logiskt orörd (endast kommentaren uppdaterad); en tagg-deploy verifierar imagen och rullar ut som förut
