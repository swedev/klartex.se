# Plan: Issue #15 — Auth: API_TOKEN for writes and the extended surface (replaces ADMIN_TOKEN) — stopgap until self-serve tokens exist

## Mål

Ersätt `ADMIN_TOKEN` med en enda `API_TOKEN` och lägg auth-gränsen där issuet vill ha den: token krävs för writes på `/api/page-templates` och för `latex`-blocket i `/api/render`, medan discovery och anonym rendering av allt annat förblir öppna. `/api/render` får en **tier-medveten** dependency som skiljer anonyma anrop (tillåtna, begränsad blockyta) från autentiserade (full blockyta; Caddys IP-tak gäller båda tills #23) i stället för att stänga endpointen. Felsvaren (`401`/`403`) ska tala om hur man får en token, och `backend/README.md` ska beskriva den nya uppdelningen.

Detta är ett stopgap: en delad token i `.env`. Konton och self-serve-tokens är #19; kvot per tier, bundle-spärr för anonyma och `429`-svaren är #23.

## Triagering

> Beslutsunderlag för detta issue.

| Fält | Värde |
|------|-------|
| **Blockeras av** | Inget. Härdningen i #20 (rate limit, body-tak, resurstak, semafor) är mergad via PR #25 och ligger på `main`. |
| **Blockerar** | #23 (anonym tier bygger på `Tier`-dependencyn som införs här) |
| **Relaterade issues** | #19 (parla, self-serve-tokens — ersätter den delade tokenen; oberoende av detta), #20 (öppet; dess punkt 3, token för `latex`-blocket, implementeras här), #23 (anonym tier — PR:en refererar med `Refs #23`, stänger inte), #21 (öppet; curl-exempel) |
| **Omfattning** | 13 filer: 3 backend-moduler, 2 testfiler, backend-README, 3 infra-filer, deploy-workflow, `llms.txt`, `index.html`, `PLAN.md` |
| **Risk** | Medel — env-var-byte som kräver ett manuellt steg på servern innan nästa release taggas; designbeslut 3 (hur tokens delas ut) är ett produktbeslut som ska bekräftas innan texterna låses |
| **Komplexitet** | Låg–Medel |
| **Säker för junior** | Nej — deploy-koordineringen (serverns `.env`) och felsvarskontraktet kräver överblick |
| **Konfliktrisk** | Låg — inga öppna planer rör `auth.py`/`render.py`; alla andra planer i `agent-docs/issue/` är mergade |

### Triagemässiga noteringar

- **PR #16 är stängd utan merge** och branchen `issue/15-api-token-auth` raderad (2026-08-28). Den la `Depends(require_api_token)` ovillkorligt på `/render`, vilket är den design issuet skrevs om för att förkasta. Inget därifrån behöver återställas: `auth.py` på `main` (`require_admin`) har redan constant-time-jämförelse, 401 vid saknad/fel token och 503 när ingen token är konfigurerad — det som PR #16 beskrev som sitt bidrag.
- **#20:s härdning ligger på `main`** (PR #25): Caddy har `rate_limit` 10/min per IP och 2 MB body-tak på `POST /api/render`; backend har semafor med max 2 samtidiga renders; compose har CPU/minne/pids-tak. Issuet är fortfarande öppet — dess punkt 3 (token för `latex`-blocket) görs här, och filläsning under kompilering är ett kärn-issue (`swedev/klartex#51`). Förutsättningen #23 nämner finns alltså, så `latex`-spärren kan läggas här utan att vänta.
- **Den delade tokenen har stor räckvidd.** Samma `API_TOKEN` som låser upp `latex`-blocket ger också `POST`/`DELETE` på *alla* registrerade bundles. Det avgör vad "hur man får en token" får lova (designbeslut 3): en förfrågningskanal, inte att produktionstokenen delas ut.
- **Caddys IP-tak gäller alla** (10/min) tills #23 differentierar. En token ger alltså full *blockyta*, inte högre kvot — dokumentationen ska säga just det.
- **Release-smoke-testet i `deploy.yml`** kör containern med `docker run` utan någon token-env och förväntar sig `200` på en anonym `/api/render` med `heading` + `text`. Den anonyma vägen måste därför fungera även när `API_TOKEN` inte är satt — bara ett *presenterat* token kräver konfiguration.
- **Versionsbump görs i release-committen**, inte i feature-PR:en (konvention sedan `Release 0.4.1`/`0.4.2`; PR #61 för #26 bumpade inte). Env-var-bytet är en breaking ops-förändring, så nästa release bör bli `0.5.0`.
- **Frontenden från #14** (`app/dist`, byggd från den omergade branchen) anropar `/api/render` anonymt utan `latex`-block, så den påverkas inte av detta issue; #23:s bundle-spärr rör den däremot senare.
- Baseline: `pytest` i `backend/` ger 43 passed lokalt (xelatex finns). CI kör hela sviten med `pytest -q -rs`; bara testerna märkta `needs_xelatex` hoppar över, så tier-testerna körs i CI.

## Angreppssätt

**Läget i koden.** `auth.py` exponerar `require_admin`, läser `ADMIN_TOKEN` och används av `POST`/`DELETE` i `page_template_router.py`. `render.py` har ingen dependency alls. Felsvaren från auth är rena strängar (`"Missing Bearer token"`), medan `/api/render` har ett dokumenterat objektkontrakt under `detail` (`type`, `message`, `path`).

**Tre byggstenar:**

1. **`auth.py` blir tier-medveten.** En `Tier`-enum (`ANONYMOUS`, `TOKEN`), en intern `_verify(authorization)` som kastar 401/503, och två dependencies ovanpå: `require_api_token` (writes: 401 om header saknas) och `render_tier` (returnerar `Tier.ANONYMOUS` när `Authorization` saknas, verifierar annars och returnerar `Tier.TOKEN`). Ett presenterat men felaktigt token ger 401 även på `/render` — det degraderas inte tyst till anonymt. Alla auth-fel får objekt-`detail` med `type` och `message`, och `message` säger hur man får en token (en konstant, `TOKEN_HOWTO`, så att texten är en rad att ändra när #19 landar).

2. **`render.py` spärrar `latex` för anonyma.** Före bundle-uppslag och semafor: om `tier is Tier.ANONYMOUS` och `req.template == "_block"`, skanna `req.data["body"]` efter block med `"type": "latex"` och svara `403` med `detail.type = "token_required"`, `detail.path` till första träffen (samma listform som övriga fel), `detail.block_type = "latex"` och en `message` som namnger blocket, säger varför och hur man får token. Skanningen är en generisk, iterativ genomgång av dict/list under `body` — den beror inte på kärnans privata `_child_block_lists` och fångar `latex` oavsett i vilken carrier (`list`, `columns`, `clause`) det ligger. Recept-mallar (`faktura` m.fl.) tolkar inga block och passerar orörda.

3. **Rename `ADMIN_TOKEN` → `API_TOKEN`** genom hela repot (backend, tester, compose, `.env.example`, infra-README, `PLAN.md`) plus en preflight i `deploy.yml` som stoppar deployen innan rsyncen om serverns `.env` saknar `API_TOKEN=`. Bytet på servern är ett manuellt steg som användaren gör (ssh) innan release-taggen pushas.

**Vad som uttryckligen inte görs här** (hör till #23): kvot per tier / Caddy-undantag för tokenbärare, spärr av registrerade bundles för anonyma, `429`-kroppar och rate-limit-headers. `Tier`-dependencyn är utformad så att #23 kan hänga in de reglerna i samma `if tier is Tier.ANONYMOUS`-gren.

## Steg

### Fas 1: `auth.py` — `API_TOKEN`, tier och strukturerade felsvar

1. Skriv om `backend/src/klartex_se/auth.py`:
   - Modul-docstring i nu-state: `API_TOKEN` gate:ar writes på `/api/page-templates` och den utökade render-ytan (`latex`-blocket); discovery och anonym rendering är öppna; stopgap tills #19.
   - `class Tier(StrEnum)`: `ANONYMOUS = "anonymous"`, `TOKEN = "token"`.
   - `TOKEN_HOWTO: str` — en mening om hur man får en token (se designbeslut 3). Används i alla 401/403-meddelanden.
   - `_verify(authorization: str | None) -> None`: läser `os.environ.get("API_TOKEN")`; tom → `503` med `detail={"type": "token_not_configured", "message": ...}`; header saknas eller saknar `Bearer `-prefix → `401` `{"type": "token_required", "message": f"... {TOKEN_HOWTO}"}` med `WWW-Authenticate: Bearer`; fel token → `401` `{"type": "invalid_token", ...}`. Jämför som bytes (`presented.encode()`, `expected.encode()`) så `secrets.compare_digest` inte kan kasta `TypeError` på icke-ASCII.
   - `require_api_token(authorization: str | None = Header(default=None)) -> None`: anropar `_verify`.
   - `render_tier(authorization: str | None = Header(default=None)) -> Tier`: `None` → `Tier.ANONYMOUS` utan att röra env; annars `_verify` och `Tier.TOKEN`.
   - Filer att ändra: `backend/src/klartex_se/auth.py`
2. `backend/src/klartex_se/page_template_router.py`: importera `require_api_token`, byt i `Depends(...)` på `create` och `delete`; docstrings "Requires `API_TOKEN`"; lägg `responses={401: {...}, 503: {...}}` med beskrivningar på de två routerna så statuskoderna finns i `/api/openapi.json` (svarskroppens form dokumenteras i README; ett OpenAPI security scheme via `HTTPBearer` är valfritt och ingår inte).
   - Filer att ändra: `backend/src/klartex_se/page_template_router.py`

### Fas 2: `render.py` — anonym tier utan `latex`

1. Lägg till `find_latex_block(body: object) -> list[str | int] | None` (modulnivå, testbar): iterativ genomgång (explicit stack, ingen rekursion — payloaden är opålitlig och djupt nästlad JSON ska inte kunna ge `RecursionError`) över dict/list med start i `["body"]`; returnerar path-listan till första dict med `type == "latex"` i dokumentordning, annars `None`. Icke-dict/list-värden hoppas över. Se designbeslut 2.
2. Signatur: `def render(req: RenderRequest, tier: Tier = Depends(render_tier)) -> Response`.
3. Först i funktionskroppen, före bundle-uppslag och semafor:
   ```python
   if tier is Tier.ANONYMOUS and req.template == "_block":
       path = find_latex_block(req.data.get("body"))
       if path is not None:
           raise HTTPException(403, detail={
               "type": "token_required",
               "block_type": "latex",
               "path": path,
               "message": (
                   "The 'latex' block passes raw LaTeX to the compiler and "
                   f"requires an API token. {TOKEN_HOWTO}"
               ),
           })
   ```
   Ingen `WWW-Authenticate` på `403` — anropet var giltigt som anonymt; headern hör till `401`.
4. Uppdatera `responses`-dicten på routern: `401` (presenterat token ogiltigt), `403` (`token_required` för `latex`), och `503`-beskrivningen så den täcker både `overloaded` och `token_not_configured`. Modul-docstringen får tier-regeln.
   - Filer att ändra: `backend/src/klartex_se/render.py`

### Fas 3: Tester

1. `backend/tests/test_page_templates.py`: `ADMIN_TOKEN` → `API_TOKEN` (konstant, `monkeypatch.setenv`, `delenv`). Skärp `test_create_requires_admin` (döp om till `..._requires_api_token`): `detail.type == "token_required"`, `message` innehåller `TOKEN_HOWTO`, `WWW-Authenticate: Bearer` finns. Nya tester: fel token → `401` med `detail.type == "invalid_token"`; `DELETE` utan och med fel token → `401`; `API_TOKEN` satt men tom → `503` (behandlas som okonfigurerad). `test_unconfigured_admin_returns_503`: `detail.type == "token_not_configured"`, och `GET /api/page-templates` samt discovery svarar `200` i samma läge.
2. `backend/tests/test_render.py` (xelatex-fritt där det går; `monkeypatch.setattr(render_module, "klartex_render", ...)` som slot-testerna redan gör):
   - Fixture `api_token(monkeypatch)` som sätter `API_TOKEN` och returnerar auth-header.
   - Anonym + `latex` på toppnivå → `403`, `detail.type == "token_required"`, `detail.block_type == "latex"`, `detail.path == ["body", 0]`, `"latex"` i `message`.
   - Anonym + `latex` nästlat i `columns` → `path == ["body", 0, "items", 1, 0]`; i `list` → `["body", 0, "items", 0, "content", 0]`; i `clause` → `["body", 0, "content", 0]`.
   - Anonym + `latex` → `403` även när båda render-platserna är upptagna (spärren ligger före semaforen) och utan att `klartex_render` anropas.
   - Token + `latex` → passerar gaten (`klartex_render` mockad, `200`).
   - Fel token på `/render` utan `latex` → `401` `invalid_token` (degraderas inte till anonymt); fel token *med* `latex` → `401`, inte `403` (verifieringen går före blockpolicyn).
   - Presenterat token + `API_TOKEN` osatt + `latex` → `503` (samma prioritet).
   - `Authorization` utan `Bearer `-prefix → `401`; presenterat token med icke-ASCII-tecken → `401`, inte `500`.
   - `API_TOKEN` ej satt: anonymt anrop utan `latex` → `200` (mockad render); presenterat token → `503`.
   - Recept-mall (`template: "faktura"`) med ett objekt `{"type": "latex"}` någonstans i `data` → ingen `403` (policyn gäller bara `_block`); anropet får svara vad schemavalideringen ger.
   - Anonymt anrop utan `latex` → oförändrat (befintliga tester täcker).
   - `/api/openapi.json`: `401` och `403` finns på `POST /api/render`, `401` och `503` på `POST`/`DELETE /api/page-templates`.
   - Enhetstest för `find_latex_block`: `None` på tom/`None`-body, icke-dict-poster i listor hoppas över, första träffen i dokumentordning, `latex` djupt i okänd struktur hittas, djupt nästlad lista (t.ex. 5 000 nivåer) ger inget `RecursionError`.
   - Filer att ändra: `backend/tests/test_page_templates.py`, `backend/tests/test_render.py`
3. Kör `pytest` i `backend/` — grönt lokalt (med xelatex). CI kör exakt `pytest -q -rs` utan xelatex; bara `needs_xelatex`-testerna får hoppa över, så kontrollera i CI-loggen att inga av de nya testerna skippas.

### Fas 4: Infra och deploy

1. `infra/docker-compose.yml`: `ADMIN_TOKEN: ${ADMIN_TOKEN}` → `API_TOKEN: ${API_TOKEN:?API_TOKEN missing in .env — see infra/README.md}` (compose stoppar innan något startas om variabeln saknas).
2. `infra/.env.example`: variabelnamn och kommentar (writes på `/api/page-templates` och `latex`-blocket i `/api/render`).
3. `infra/README.md`: raden om att `.env` "bär ADMIN_TOKEN" → `API_TOKEN`; under "Uppgradera backend-versionen" ett stycke om `.env`-steget vid övergången till `0.5.0` (lägg till `API_TOKEN`, behåll `ADMIN_TOKEN` under rollback-fönstret, ta bort den efteråt).
4. `.github/workflows/deploy.yml`, steget "Sync infra and landing page": i det befintliga ssh-blocket som kontrollerar att `.env` finns, lägg till `grep -Eq '^API_TOKEN=.+' /home/klartex/klartex/.env || { echo "API_TOKEN is not set in /home/klartex/klartex/.env — see infra/README.md" >&2; exit 1; }` (icke-tomt värde, samma krav som compose-`:?`) så deployen stannar före rsyncen och den körande stacken lämnas orörd.
   - Filer att ändra: `infra/docker-compose.yml`, `infra/.env.example`, `infra/README.md`, `.github/workflows/deploy.yml`

### Fas 5: Dokumentation

1. `backend/README.md`:
   - Endpoint-tabellen får en kolumn **Token**: `Nej` för health/discovery/`GET page-templates`; `Nej — utom `latex`-blocket` för `POST /api/render`; `Ja` för `POST`/`DELETE /api/page-templates`.
   - Nytt avsnitt **Autentisering**: `API_TOKEN` i env, `Authorization: Bearer <token>`, de två nivåerna (anonym: alla block utom `latex`; token: full blockyta — Caddys IP-tak gäller båda tills #23), att ett presenterat felaktigt token ger `401` även på `/api/render`, och `503` när instansen saknar token. Hänvisa till #19 för self-serve och #23 för kvoter.
   - Feltabellen för `/api/render` får rader: `token_required` (403, anonymt anrop med `latex`-block, `path` alltid, plus `block_type`), `invalid_token` (401), `token_not_configured` (503; `503` betyder alltså antingen `overloaded` eller detta — `detail.type` skiljer). Notera att `POST`/`DELETE /api/page-templates` ger `401` (`token_required`/`invalid_token`) och `503` (`token_not_configured`) med samma `detail`-form; `403` förekommer bara på `/api/render`.
2. `llms.txt`: stycket "`POST /api/render` need no token" → precisera: no token needed except for the `latex` block, which answers `403` with a `detail` that names the block and how to get a token; a token unlocks the full block surface, not a higher rate limit. Stycket om att det "inte finns något sätt att få en token" ersätts med samma formulering som `TOKEN_HOWTO`.
3. `index.html`, avsnittet "Vad som är öppet" — båda styckena: (a) "Rendering och schema-uppslagning är öppna och kräver ingen token" → tillägg att `latex`-blocket (rå LaTeX) kräver token; (b) stycket om egen sidmall säger idag att `POST /api/page-templates` svarar `401` "tills vidare" eftersom konton inte finns — skrivs om så det stämmer med `TOKEN_HOWTO` (åtkomst på förfrågan tills konton lanseras), utan att lova mer än beslut 3 medger.
4. `PLAN.md`: beslutstabellens rad **Page-template-registry** (`ADMIN_TOKEN` → `API_TOKEN`); risktabellens rad om `/api/render` — "bör `latex`-blocket inte nås anonymt (#23)" skrivs om i nu-state: `latex`-blocket kräver token.
   - Filer att ändra: `backend/README.md`, `llms.txt`, `index.html`, `PLAN.md`

### Fas 6: Release-koordinering (utanför PR:en, körs av användaren)

1. Merge av PR:en till `main` (CI kör testerna utan xelatex).
2. På servern, innan taggen pushas: lägg till `API_TOKEN=<samma värde>` i `/home/klartex/klartex/.env` och **behåll `ADMIN_TOKEN`-raden tills vidare** — en rollback till `v0.4.x` (`workflow_dispatch` från den taggen) syncar den gamla compose-filen, som läser `ADMIN_TOKEN`, och skulle annars ge `503` på writes. Ta bort `ADMIN_TOKEN` först när `0.5.0` har legat stabilt. Kräver ssh — användaren gör det själv. Steget dokumenteras i `infra/README.md` under "Uppgradera backend-versionen".
3. Release-commit: bumpa `backend/pyproject.toml` och `__init__.py` till `0.5.0`, tagga `v0.5.0`. Deployen preflightar `.env`, smoke-testar anonym render i CI och deployar.
4. Verifiera mot produktion: anonym curl med `heading`/`text` → `200 application/pdf`; samma med ett `latex`-block → `403` med `token_required`; med `Authorization: Bearer <token>` → `200`; `POST /api/page-templates` utan token → `401` vars `message` säger hur man får token.
5. PR-bodyn: `Closes #15`, `Refs #23` (den implementerar en del av #23:s acceptanskriterier utan att stänga det) och `Refs #20` (punkt 3).

## Filöversikt

| Fil | Åtgärd | Syfte |
|-----|--------|-------|
| `backend/src/klartex_se/auth.py` | Ändra | `API_TOKEN`; `Tier`; `TOKEN_HOWTO`; `_verify`; `require_api_token`; `render_tier`; objekt-`detail` på 401/503 |
| `backend/src/klartex_se/page_template_router.py` | Ändra | `Depends(require_api_token)`; docstrings; `responses` 401/503 |
| `backend/src/klartex_se/render.py` | Ändra | `find_latex_block`; `tier: Tier = Depends(render_tier)`; 403 `token_required` för anonymt `latex`; `responses` 401/403; docstring |
| `backend/tests/test_page_templates.py` | Ändra | `API_TOKEN`; skärpta 401/503-assertions; nytt `invalid_token`-test |
| `backend/tests/test_render.py` | Ändra | Tier-tester (anonym/latex/nästlat/token/fel token/okonfigurerad), enhetstester för `find_latex_block` |
| `backend/README.md` | Ändra | Token-kolumn i endpoint-tabellen; avsnitt Autentisering; nya feltyper i tabellen |
| `infra/docker-compose.yml` | Ändra | `API_TOKEN: ${API_TOKEN:?...}` |
| `infra/.env.example` | Ändra | `API_TOKEN` med ny kommentar |
| `infra/README.md` | Ändra | `.env` bär `API_TOKEN`; övergångssteget (`ADMIN_TOKEN` kvar under rollback-fönstret) |
| `.github/workflows/deploy.yml` | Ändra | Preflight: `.env` måste ha `API_TOKEN=` innan rsync |
| `llms.txt` | Ändra | `latex`-blocket kräver token; hur man får token |
| `index.html` | Ändra | "Vad som är öppet": `latex`-blocket kräver token |
| `PLAN.md` | Ändra | `API_TOKEN` i beslutstabellen; risktabellen i nu-state |

## Berörda kodområden

- `backend/src/klartex_se/` (auth, render, page-template-router)
- `backend/tests/`
- `infra/` (compose, env, README)
- `.github/workflows/deploy.yml`
- Rotdokument: `backend/README.md`, `llms.txt`, `index.html`, `PLAN.md`

## Designbeslut

> Icke-triviala val gjorda under planeringen. Feedback välkommen; annars implementeras enligt dessa.

### 1. Presenterat men felaktigt token ger 401 på `/render` — inte tyst anonymt
**Alternativ:** A) fel token → `401 invalid_token`; B) fel token → behandla som anonymt (fungerar utan `latex`)
**Beslut:** A
**Motivering:** Ett agent-anrop med feltypat token ska få veta det, inte lyckas "ibland" och sedan få ett oförklarligt `403` första gången ett `latex`-block dyker upp. B skulle också göra det omöjligt att skilja en trasig integration från en avsiktligt anonym. *Proveniens: agentens bedömning — öppen att ifrågasätta.* Issuet säger bara att dependencyn ska skilja anonyma från autentiserade, inte vad ett ogiltigt token betyder.

### 2. Generisk skanning av `data["body"]` efter `type == "latex"` när `template == "_block"`, inte kärnans carrier-lista
**Alternativ:** A) iterativ genomgång av dict/list under `data["body"]`, bara för `_block`; B) återanvänd `klartex.renderer._child_block_lists` för schema-medveten gång; C) bara `data["body"]` på toppnivå utan nästling; D) hela `data` oavsett mall
**Beslut:** A
**Motivering:** B är privat API i kärnan och går sönder tyst vid refaktorering; C missar `latex` nästlat i `list`/`columns`/`clause` (kärnan validerar just dessa nästlingar); D skulle ge ett vilseledande `403` för ett recept-objekt som råkar innehålla `"type": "latex"` fast kärnan aldrig tolkar det som block. A är ~15 rader, speglar var kärnan faktiskt tolkar block (`_block` → `data["body"]`), fångar varje carrier — även sådana som tillkommer senare — och felar åt rätt håll inom `body`: ett `latex` på ett ställe där kärnan ändå skulle avvisa det ger `403` i stället för `400`, vilket är oskadligt. Iterativ i stället för rekursiv så att djupt nästlad JSON inte kan ge `RecursionError`. Pathen byggs under gången i samma listform som `detail.path` redan använder. *Proveniens: agentens bedömning.*

### 3. Kanalen för "hur man får en token"
**Alternativ:** A) `TOKEN_HOWTO` säger att åtkomst ges på förfrågan via `kontakt@klartex.se` tills self-serve-konton finns; B) peka på `https://klartex.se/llms.txt` och låta den säga att det inte finns någon väg än; C) länk till issue #19
**Beslut:** A, som en enda konstant i `auth.py` som `llms.txt` och `index.html` upprepar ordagrant
**Motivering:** Issuet säger att 401-kroppen ska tala om *hur* man får en token, vilket förutsätter att det finns en väg; den enda som existerar före #19 är att be om en. `kontakt@klartex.se` är redan projektets publika kontaktadress (ACME-kontakt i `infra/Caddyfile`). Konstanten gör bytet till self-serve-URL:en en rad. **Viktigt:** tokenen är en enda delad hemlighet som också ger `POST`/`DELETE` på alla registrerade bundles, och rotation slår ut alla mottagare samtidigt. Texten ska därför lova en *förfrågan* ("access on request"), inte att produktionstokenen skickas ut; vem som faktiskt får den, och när den roteras, är ett driftbeslut utanför koden. *Proveniens: agentens bedömning — det här är ett produktbeslut och ska bekräftas av användaren innan `TOKEN_HOWTO`, `llms.txt` och `index.html` låses. Om svaret är "inga tokens till utomstående" blir B rätt val, med ärlig text i alla tre.*

### 4. `403` för anonymt `latex`, `401` för saknat/fel token på writes
**Alternativ:** A) `403 token_required` för `latex`; B) `401` överallt
**Beslut:** A
**Motivering:** *Proveniens: användarbeslut* — #23 specificerar `403` för `latex`-blocket ("names the block type that was rejected and why") och #15 `401` för saknat token på writes. Anropet var giltigt som anonymt; det är *blocket* som kräver mer, vilket är `403`-semantik. `WWW-Authenticate: Bearer` sätts bara på `401`, där den är obligatorisk.

### 5. Strukturerad `detail` även på auth-fel
**Alternativ:** A) `detail` som objekt `{type, message}` på 401/403/503; B) behåll strängar som idag
**Beslut:** A
**Motivering:** `/api/render` har redan ett dokumenterat objektkontrakt (`type`, `message`, `path`) som README beskriver som "alla fel efter request-parsningen". Att auth-felen på samma endpoint kommer som strängar bryter det, och #23:s `429`-kroppar kommer behöva samma form. Övriga sträng-`detail` i page-template-routern (404/409/400) lämnas orörda — utanför scope. *Proveniens: befintlig konvention (backend/README.md, "Felsvar från /api/render"), utsträckt till auth.*

### 6. Kvot och bundle-spärr lämnas till #23; Caddy rörs inte
**Alternativ:** A) bara `Tier` + `latex`-spärr här; B) även undanta tokenbärare från Caddys IP-limit (`match` på frånvarande `Authorization`) och spärra registrerade bundles för anonyma
**Beslut:** A
**Motivering:** *Proveniens: användarbeslut* — #23 tar uttryckligen "fine-grained per-tier quota" och bundle-spärren, och #20:s plan lämnade `latex`-punkten till "#23-arbetet", vilket #15 nu gör i sin tier-medvetna form. B är billigt men gör PR:en till halva #23 utan dess `429`-kontrakt. `Tier`-grenen i `render()` är där #23 hänger in resten.

### 7. Hård fail när `API_TOKEN` saknas på servern
**Alternativ:** A) `${API_TOKEN:?}` i compose + preflight-grep i `deploy.yml`; B) `${API_TOKEN:-${ADMIN_TOKEN}}`-fallback i compose; C) ingen kontroll
**Beslut:** A
**Motivering:** Utan kontroll deployar en glömd rename en instans där writes ger `503` och tokenbärare får `503` — fullt fungerande anonymt, så det märks sent. B döljer bytet i stället för att slutföra det. Preflighten i `deploy.yml` ligger i steget som redan verifierar att `.env` finns, före rsync, så stacken lämnas orörd och felet säger exakt vad som ska göras; compose-`:?` fångar samma sak vid manuell `docker compose up`. *Proveniens: agentens bedömning.*

### 8. Versionsbump i release-committen, `0.5.0`
**Alternativ:** A) bump i PR:en; B) bump i separat release-commit (0.5.0)
**Beslut:** B
**Motivering:** *Proveniens: befintlig konvention* — `Release 0.4.1`/`0.4.2` är egna commits, och PR #61 bumpade inte. Minor eftersom env-variabeln byter namn (ops-breaking).

## Verifieringschecklista

- [ ] `pytest` i `backend/` grönt lokalt (med xelatex) och i CI (utan)
- [ ] Anonym `POST /api/render` med `heading`+`text` → `200 application/pdf` (också med `API_TOKEN` osatt — smoke-testet i `deploy.yml`)
- [ ] Anonym `POST /api/render` med `latex`-block → `403`, `detail.type == "token_required"`, `detail.block_type == "latex"`, `detail.path` pekar på blocket, `message` säger hur man får token
- [ ] Samma med `latex` nästlat i `columns`/`list`/`clause` → `403` med rätt `path`
- [ ] `POST /api/render` med giltig token och `latex`-block → `200`
- [ ] `POST /api/render` med felaktig token (utan `latex`) → `401 invalid_token`; med felaktig token och `latex` → `401` (inte `403`)
- [ ] `template: "faktura"` med `{"type": "latex"}` i datan → ingen `403`
- [ ] `POST`/`DELETE /api/page-templates` utan token → `401 token_required`, `WWW-Authenticate: Bearer`, `message` innehåller `TOKEN_HOWTO`; med fel token → `401 invalid_token`; med token → `201`/`204`
- [ ] `API_TOKEN` osatt eller tom + presenterat token → `503 token_not_configured` på både `/render` och `/page-templates`; discovery och `GET /api/page-templates` → `200` i samma läge
- [ ] `grep -rn ADMIN_TOKEN` i repot (utanför `agent-docs/`) → inga träffar
- [ ] `/api/openapi.json` listar 401/403 på `/api/render` och 401/503 på writes; `503`-beskrivningen på `/api/render` täcker båda betydelserna
- [ ] `backend/README.md`, `llms.txt`, `index.html` (båda styckena under "Vad som är öppet") och `TOKEN_HOWTO` säger samma sak om hur man får token, och att token ger full blockyta — inte högre kvot
- [ ] Designbeslut 3 bekräftat av användaren innan texterna låses
- [ ] Deploy-preflight: `.env` utan icke-tomt `API_TOKEN=` stoppar deployen före rsync (läs ssh-blocket)
- [ ] `infra/README.md` beskriver att `ADMIN_TOKEN` behålls i `.env` under rollback-fönstret
- [ ] Efter release: produktionsverifiering enligt Fas 6 steg 4
