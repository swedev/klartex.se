# Plan: Issue #17 — Kom ikapp klartex 0.14.0: bumpa pinnen, hantera breaking changes, uppdatera sajtinnehåll och CLAUDE.md

## Mål

Bumpa `klartex`-pinnen från `0.11.1` till `0.14.0` på båda ställena (pyproject + Dockerfile), verifiera backend mot breaking changes i 0.12.0 och de nya `asset_dir`-beteendena i 0.13.0, korrigera sajtinnehållet (`index.html`, `llms.txt`) som listar fel mallar och delvis påhittade blocktyper, och skriva om CLAUDE.md-avsnittet som fortfarande pekar på det borttagna `klartex serve`.

## Triagering

> Beslutsunderlag för detta issue.

| Fält | Värde |
|------|-------|
| **Blockeras av** | Inget |
| **Blockerar** | Inget hårt; #21 (generera llms.txt från API:t) bygger vidare på korrekt API-innehåll, #14 (Tiptap fas 1) mår bra av att kärnan är uppe på 0.14.0 |
| **Relaterade issues** | #21 (generera sajtinnehåll från API:t — långsiktiga fixen för de handunderhållna listorna), #22 (PLAN.md föråldrad — PLAN.md-uppdateringar lämnas dit), #15 (API_TOKEN-auth — grenen `issue/15-api-token-auth` rör `auth.py`/`page_template_router.py`/`main.py`, inte denna plans filer; se noteringar om merge-ordning) |
| **Omfattning** | ~8 filer: 5 i `backend/`, sajtroten (`index.html`, `llms.txt`) och `CLAUDE.md` |
| **Risk** | Låg |
| **Komplexitet** | Låg–Medel |
| **Säker för junior** | Ja |
| **Konfliktrisk** | Låg (inga andra öppna planer i `agent-docs/issue/`; branch `issue/15-api-token-auth` rör `page_template_router.py`/`auth.py` men denna plan ändrar inte de filerna) |

### Triagemässiga noteringar

- Verifierat mot kärnans `../klartex/CHANGELOG.md`: issuets beskrivning av 0.12.0–0.14.0 stämmer. 0.12.0 har de två breaking changes som listas; 0.13.0 och 0.14.0 är additiva.
- Kärnan finns lokalt i `../klartex/`, men checkouten står på en feature-gren (`issue/40-...`) förbi `v0.14.0`. All faktaverifiering (block-/mallistor, breaking changes) görs därför mot **taggen `v0.14.0`** (`git ls-tree v0.14.0 ...`), inte mot working tree. Inventeringen vid taggen är bekräftad: 20 blockscheman, 7 recept + `_block`.
- `app/` i repo-roten är otrackad build-output (`dist/`, `node_modules/`) — det finns ingen incheckad frontend på `main` som parsar felsträngar. Frontend-arbetet lever i #14/#15-grenarna; genomgången av felsträngsparsning görs där det är relevant (se Fas 2).
- **Merge-ordning mot #15:** grenen `issue/15-api-token-auth` gate:ar skriv-endpoints (`page_template_router`, `auth.py`, `main.py`) men lämnar `/render` öppen — ingen filkonflikt med denna plan och sajtens curl-exempel behöver ingen auth. Rekommendation: landa #15 först och rebasa denna PR, annars räcker en trivial rebase åt andra hållet.

## Angreppssätt

Detta är ett underhålls-/ikappissue i fyra oberoende delar som med fördel görs i en och samma PR eftersom sajtinnehållet (del 4) beskriver kärnversionen som del 1 bumpar till:

1. **Versionsbump** är mekanisk men måste träffa båda pinnarna — `backend/pyproject.toml:7` och `backend/Dockerfile:35` — annars kör den byggda imagen kvar på gammal kärna.
2. **Breaking changes 0.12.0**: kodgenomgången är i praktiken en verifiering. Grep visar att backend inte skickar några `signatures`-payloads med två parter (enda träffen är `test_discovery.py:45` som bara kollar att blocktypen *finns*), och `render.py` skickar felmeddelanden vidare oparsade (`e.message` rakt in i HTTP-detail). Ingen kod förväntas behöva ändras — men genomgången dokumenteras och testsviten körs mot 0.14.0 som bevis.
3. **`asset_dir` 0.13.0**: registret (`page_templates.py` / `get_bundle_path`) validerar redan att bundle-katalogen finns innan den skickas till `render()`, så det nya `ValueError`-beteendet är i praktiken täckt; en race (bundle raderas mellan uppslag och render) fångas av `render.py`:s befintliga `except ValueError` → 400. Det nya cwd-beteendet (explicit relativa referenser som `./logo.pdf` fungerar nu) är en *förbättring* för registrerade mallar och ska dokumenteras i registrets docstring/README, inte kodas runt.
4. **Sajtinnehåll + CLAUDE.md**: `index.html` och `llms.txt` uppdateras för hand mot kärnans faktiska register (7 mallar + `_block`, 20 blocktyper — verifierade mot `../klartex/klartex/schemas/blocks/` och `templates/`). `index.html` marknadsför dessutom fortfarande `klartex serve` som togs bort i 0.11.0 — den raden byts mot en hänvisning till HTTP-API:t på `api.klartex.se`. CLAUDE.md:s kärnprincip-punkt 1 skrivs om att peka på `backend/` (`klartex-se-backend`).

Automatgenerering av llms.txt är uttryckligen utanför scope — det är #21.

## Steg

### Fas 1: Bumpa beroendet

1. Bumpa `klartex==0.11.1` → `klartex==0.14.0`
   - Filer att ändra: `backend/pyproject.toml` (rad 7), `backend/Dockerfile` (rad 35)
2. Bumpa backendens egen version `0.2.1` → `0.2.2` (dependency-ikapp, ingen ändring i backendens API-yta)
   - Filer att ändra: `backend/pyproject.toml` (rad 3)
3. Installera om lokalt och kör testsviten som snabb upgrade-feedback (slutverifiering sker i Fas 6)
   - Från `backend/`: `./.venv/bin/python -m pip install -e '.[dev]'` (eller motsvarande explicit interpreter för den venv som används), följt av `./.venv/bin/python -m pip check`
   - `./.venv/bin/python -m pytest -rs tests/` — `-rs` så att skippade render-tester syns; render-testerna kräver xelatex på PATH och får inte vara skippade i slutverifieringen

### Fas 2: Verifiera mot breaking changes i 0.12.0

1. `signatures`/`contract_intro`: bekräfta att inga payloads/exempel/tester i backend förlitar sig på tvåparts-heuristiken
   - Grep-genomgång redan gjord: enda `signatures`-referensen är `backend/tests/test_discovery.py:45` (närvarokoll, ingen rendering) — inget att ändra
   - Dokumentera slutsatsen i PR-bodyn
2. Felsträngsformat (`body[i]` i stället för `index i`): bekräfta att inget parsar/matchar felsträngar
   - `backend/src/klartex_se/render.py` skickar `e.message`/`str(e)` oparsat vidare som `detail.message` — inget att ändra
   - `backend/tests/test_render.py:52` asserterar bara `"text" in detail["message"]` — robust mot formatbytet
   - Lägg till ett test som asserterar att `body[0]` förekommer i `detail.message` vid blockvalideringsfel — bevisar att 0.12-formatet når klienter oförändrat
     - Filer att ändra: `backend/tests/test_render.py`
   - Obs: blockvalideringsfel wrappas av kärnan som `ValueError` → backend returnerar bara `{"type": "input_error", "message": ...}`; `detail.path` finns enbart för det separata `jsonschema.ValidationError`-fallet. Frontend finns inte incheckad på `main`; notera i PR-bodyn att #14/#15-grenarna inte ska matcha på felsträngsformat (strukturerad path för blockfel är i så fall en egen backend-ändring, utanför scope här)

### Fas 3: `asset_dir`-beteenden i 0.13.0

1. Verifiera felhanteringen för ogiltig `asset_dir`
   - `get_bundle_path()` i `backend/src/klartex_se/page_templates.py` kräver redan att katalogen + `_metadata.json` finns → `PageTemplateNotFound` → 400 innan `render()` nås
   - Race-fallet (bundle raderas efter uppslag) → kärnans nya `ValueError` → fångas av `render.py`:s befintliga `except ValueError` → 400 `input_error`. Acceptabelt; ingen kodändring
2. Dokumentera det nya asset-upplösningsbeteendet för registrerade sidmallar
   - Dokumentera exakt distinktionen: bara filnamn (`logo.pdf`) löses mot bundlen först med process-cwd som fallback; `./`-prefixade namn (`./logo.pdf`) löses enbart mot bundle-katalogen, utan cwd-fallback. Krock mellan bundle-asset och cwd-fil löses till bundlens kopia
   - Rekommendera **inte** `../`-sökvägar: registrets asset-namnsregler tillåter inga sökvägsseparatorer i uppladdningar, så ingen bundle kan skapa den layouten själv, och parent-relativa referenser skulle nå syskonbundles — fel sida av trust-gränsen inför framtida per-org-uppladdningar. Nämn dem inte som funktion
   - Filer att ändra: docstringen i `backend/src/klartex_se/page_templates.py` (asset-avsnittet) och `backend/README.md` (konsumentvänd endpoint-dokumentation)

### Fas 4: Uppdatera sajtinnehållet

1. `index.html`
   - Mall-tabellen (rad 57–62): komplettera med `kvitto`, `balansrakning`, `resultatrakning`, `budgetrapport`, `sie-exportrapport` (beskrivningar från kärnans registry/schema-descriptions)
   - Usage-blocket (rad 73–74): ta bort `# Start HTTP API server` / `klartex serve --port 8000`; ersätt med en rad som pekar på HTTP-API:t på `https://api.klartex.se` (t.ex. curl mot `/render`)
2. `llms.txt`
   - Mall-listan (rad 27–29): samma komplettering som index.html
   - Blocktyp-listan (rad 88): ersätt med den verifierade listan om 20 typer: `agenda, budgettabell, callout, clause, columns, description_list, form, heading, latex, list, name_roster, notapparat, page_break, parties, quote, resultatrakning, signatures, table, text, title_page` (tar bort de tre påhittade `metadata_table`, `attendees`, `adjuster_signatures`)
   - Kort omnämnande av 0.14.0-nyheterna som är relevanta för konsumenter: `page_template`-objektform (`font`, `header_font`, `footer`) i recept, fakturans/kvittots `sender`/`logo`/`footer`, svenskt talformat som default med `number_format`-överstyrning. Hålls kort — llms.txt ska genereras från API:t i #21
3. Verifiera listorna mot källan vid taggen: `git -C ../klartex ls-tree --name-only v0.14.0 klartex/templates/` (7 recept + `_block`) och `... klartex/schemas/blocks/` (20 scheman), alternativt `GET /blocks` mot en lokal server med 0.14.0

### Fas 5: Skriv om CLAUDE.md

1. Kärnprincip-avsnittet, punkt 1: byt "`klartex serve` (HTTP-API:t i kärnan)" mot backendens HTTP-API
   - Ny lydelse i stil med: "Anropa `klartex-se-backend` (`backend/` i detta repo, som importerar `klartex` som library) för all PDF-rendering — aldrig själv producera LaTeX."
   - Skrivs i nu-state, utan hänvisning till att servern "togs bort" (historiken bor i PLAN.md:22 och kärnans CHANGELOG)
   - Filer att ändra: `CLAUDE.md` (rad 25)

### Fas 6: Slutverifiering och avslut

1. Kör hela testsviten mot 0.14.0 med `-rs` och bekräfta att render-testerna faktiskt kördes (inte skippades pga saknad xelatex)
2. Sanity-rendera ett dokument via `/render` med en registrerad page-template-bundle (skapa en tillfällig bundle med en asset som refereras både som bara filnamn och `./`-prefixad) för att bekräfta `asset_dir`-flödet mot 0.13.0-beteendet
3. Docker-imagen byggs om vid nästa deploy (pinnen i Dockerfile räcker); ingen separat åtgärd i denna PR utöver bumpen

## Filöversikt

| Fil | Åtgärd | Syfte |
|-----|--------|-------|
| `backend/pyproject.toml` | Ändra | Bumpa `klartex==0.11.1` → `0.14.0` (rad 7) samt backend-versionen `0.2.1` → `0.2.2` (rad 3) |
| `backend/Dockerfile` | Ändra | Bumpa samma klartex-pin (rad 35) |
| `backend/tests/test_render.py` | Ändra | Nytt test: blockvalideringsfel bär `body[0]`-path i `detail.message` |
| `backend/src/klartex_se/page_templates.py` | Ändra | Docstring: dokumentera asset-upplösning (bara filnamn vs `./`-prefix) mot bundle-katalogen |
| `backend/README.md` | Ändra | Konsumentvänd notis om asset-upplösning för registrerade bundles |
| `index.html` | Ändra | Komplett mall-tabell; ta bort `klartex serve`-exemplet, peka på api.klartex.se |
| `llms.txt` | Ändra | Komplett mall-lista; korrekt blocktyp-lista (20 st); kort 0.14.0-nytt |
| `CLAUDE.md` | Ändra | Kärnprincip punkt 1: peka på `backend/` i stället för borttagna `klartex serve` |

## Berörda kodområden

Lista de primära kataloger/områden som planen berör (för konfliktdetektering):
- `backend/` (pyproject, Dockerfile, `src/klartex_se/page_templates.py`, README)
- Sajtroten (`index.html`, `llms.txt`)
- `CLAUDE.md`

## Designbeslut

> Icke-triviala val gjorda under planeringen. Feedback välkommen; annars implementeras enligt dessa.

### 1. Branding-ytan (registret vs kärnans `page_template`-objektform) avgörs inte här
**Alternativ:** A) Utse rekommenderad yta för branding nu (registret eller kärnans nya objektform med `font`/`footer`) vs B) dokumentera att båda finns och lämna beslutet öppet
**Beslut:** B
**Motivering:** Issuet säger "värt att avgöra vilken yta som är den rekommenderade för branding framöver" — det är ett produktbeslut utan användarbeslut i ryggen ännu (proveniens: agentens bedömning, öppet att ifrågasätta). Detta issue är ett ikapp-issue; att utse en rekommenderad yta hör hemma i ett eget beslut (lämpligen i anslutning till #21/#14 där ytan faktiskt exponeras). Här nämns bara objektformen i llms.txt som existerande funktionalitet.

### 2. Sajtlistorna fixas för hand nu, generering väntar
**Alternativ:** A) Handuppdatera `index.html`/`llms.txt` nu vs B) bygga genereringen från API:t direkt
**Beslut:** A
**Motivering:** Användarbeslut — issuet säger explicit att generering är "det separata issuet" (#21). Handfixen gör innehållet korrekt idag; #21 tar bort rotorsaken.

### 3. `klartex serve`-exemplet i `index.html` ersätts med api.klartex.se
**Alternativ:** A) Bara ta bort serve-raderna vs B) ersätta med curl-exempel mot `https://api.klartex.se`
**Beslut:** B
**Motivering:** Agentens bedömning (öppen att ifrågasätta): HTTP-ytan finns fortfarande, den bor bara i backenden — att visa den är mer korrekt än att tyst tappa funktionen från sajten, och llms.txt hänvisar redan till "the HTTP API". Domänen `api.klartex.se` är etablerad i PLAN.md:170.

### 4. Exakt pin `==0.14.0` behålls (ingen range)
**Alternativ:** A) `==0.14.0` vs B) `>=0.14,<0.15`
**Beslut:** A
**Motivering:** Befintlig konvention (pinnen är exakt idag, på båda ställena); reproducebara image-byggen. Bump sker medvetet per version, som detta issue visar.

### 5. Ingen kodändring för `asset_dir`-valideringen
**Alternativ:** A) Lägga till explicit validering/eget felmeddelande i registret före `render()` vs B) lita på befintlig kedja (`get_bundle_path` → 404/400; race → kärnans `ValueError` → befintlig 400)
**Beslut:** B
**Motivering:** Registret validerar redan existens + metadata före render; det enda ovaliderade fallet är en TOCTOU-race som kärnans nya `ValueError` numera gör högljudd i stället för tyst no-op — en förbättring som redan mappas till 400 av `render.py`. Extra validering vore dubblering.

## Verifieringschecklista

- [ ] `grep -rn "0.11.1" backend/` ger noll träffar efter bumpen (båda pinnarna tagna)
- [ ] `pytest -rs backend/tests/` grönt mot `klartex==0.14.0`, och render-testerna kördes (inte skippade)
- [ ] Nytt test bekräftar att `body[0]`-formatet når klienten i `detail.message`
- [ ] `pip check` rent i backend-venven efter ominstallation
- [ ] Sanity-rendering via `/render` med registrerad bundle (asset_dir-flödet) ger PDF
- [ ] `index.html` listar `_block` + alla 7 recept; inga `klartex serve`-referenser kvar
- [ ] `llms.txt` blocktyp-lista matchar exakt `git -C ../klartex ls-tree --name-only v0.14.0 klartex/schemas/blocks/` (20 typer; `metadata_table`/`attendees`/`adjuster_signatures` borta)
- [ ] `CLAUDE.md` kärnprincip punkt 1 pekar på `backend/`, ingen `klartex serve`-referens kvar i CLAUDE.md
- [ ] Kantfall: valideringsfel via `/render` returnerar fortfarande strukturerad 400 (nya `body[i]`-formatet passerar oparsat)
