# backend/

FastAPI-app som exponerar HTTP-API:t som klartex.se frontend använder: discovery, auth och nivåpolicy, sidmallsregistret och hela den publika `/api`-ytan.

Här kompileras ingenting. `POST /api/render` avgör vad anroparen får göra, läser sidmallen ur registret och skickar arbetet vidare till render-tjänsten `ghcr.io/swedev/klartex-render` — kärnans egen artefakt, byggd och publicerad av `swedev/klartex` vid varje release, och den enda process som kör `xelatex`. Den når inte instansens hemligheter, har ingen volym och ligger på ett internt nätverk utan väg ut.

`klartex` är ändå ett beroende här: discovery-scheman läses direkt ur paketet, utan TeX Live. Adressen till render-tjänsten står i `RENDER_URL` (default `http://render:8000`).

## Endpoints

| Metod & path | Vad | Token |
|--------------|-----|-------|
| `GET /api/health` | Liveness — används av Docker healthcheck | Nej |
| `POST /api/auth/request-code` | Mejla en sexsiffrig engångskod till en adress | Nej |
| `POST /api/auth/code` | Lös in koden och få en sessionskaka | Nej |
| `POST /api/auth/logout` | Släng sessionen | Nej |
| `GET /api/me` | Vem anroparen är inloggad som | Sessionskaka |
| `GET /api/templates` | Lista mallar (block-engine + recipe) | Nej |
| `GET /api/templates/{name}/schema` | JSON Schema för en mall | Nej |
| `GET /api/blocks` | Lista block-engine-blocktyper | Nej |
| `GET /api/blocks/{name}/schema` | JSON Schema för en blocktyp | Nej |
| `POST /api/render` | JSON in, PDF out via render-tjänsten. Max 2 anrop i luften — fler ger 503 | Nej — utom `latex`-blocket |
| `GET /api/page-templates` | Lista registrerade sidmalls-bundles | Nej |
| `GET /api/page-templates/{name}` | Metadata för en bundle | Nej |
| `POST /api/page-templates` | Registrera eller ersätt en bundle (`.tex.jinja` + assets, base64) | Ja |
| `DELETE /api/page-templates/{name}` | Ta bort en bundle | Ja |

Multipart-varianten `/api/render-with-assets` (logo + `.tex.jinja`-upload) tillkommer i nästa iteration.

## Autentisering

Instansen bär en delad token i env-variabeln `API_TOKEN` (se `infra/.env.example`). Den presenteras som `Authorization: Bearer <token>`.

Två nivåer:

| Nivå | Vad som går att göra |
|------|----------------------|
| Anonym (ingen `Authorization`-header) | Discovery, `GET` på registret, och rendering av alla block **utom** `latex` |
| Token | Hela blockytan, inklusive `latex`, plus `POST`/`DELETE` på `/api/page-templates` |

En token låser upp *blockytan*, inte en högre kvot: Caddys tak på 10 anrop per minut och IP gäller båda nivåerna (kvot per nivå hör till #23).

Ett presenterat men felaktigt token ger `401` även på `/api/render` — anropet degraderas inte tyst till anonymt, så en trasig integration går att skilja från ett avsiktligt anonymt anrop. Saknas `API_TOKEN` på instansen svarar varje anrop som presenterar en token `503`; de anonyma vägarna fungerar ändå.

Tokenen är ett stopgap: en enda hemlighet som ger full åtkomst till alla bundles. Konton och self-serve-tokens är #19. Åtkomst ges på förfrågan tills dess — mejla kontakt@klartex.se.

## Konton och inloggning

Inloggning är e-postadress plus en sexsiffrig engångskod, och ingenting annat. En magisk länk skulle dra in problemet med mejlskannrar — ett `GET` som inte får förbruka inloggningen — utan att ge något: koden skrivs in i samma vy som bad om den, så klienten behöver inget eget tillstånd mellan de två stegen.

Det finns ingen allowlist. Vem som helst med en fungerande brevlåda kan logga in, och första inloggningen skapar användaren plus en en-persons-organisation för den. Organisationen är det parkopplade maskiner kommer att höra till.

```bash
curl -X POST http://localhost:8000/api/auth/request-code \
  -H 'Content-Type: application/json' -d '{"email":"du@example.com"}'

curl -X POST http://localhost:8000/api/auth/code -c cookies.txt \
  -H 'Content-Type: application/json' -d '{"email":"du@example.com","code":"123456"}'

curl -b cookies.txt http://localhost:8000/api/me
```

Tre egenskaper håller ihop flödet:

- **Enumeration-säkerhet.** `request-code` svarar likadant för en adress som har konto, en som inte har det, och en som fortfarande ligger inne i sin cooldown på 60 sekunder. Inlösen svarar likadant för fel, förbrukad, utgången och slutförsökt kod.
- **Ingenting uppspelningsbart lagras.** Koden ligger som HMAC nycklad med `LOGIN_CODE_SECRET`, som aldrig når databasen; sessionstoken som ren sha256.
- **Kapplöpningar kan inte dubbelspendera.** En guardad `UPDATE` förbrukar koden, och begäransvägen serialiserar per adress på ett `pg_advisory_xact_lock`, så två samtidiga anrop inte kan lämna två levande koder efter sig.

En kod gäller i 15 minuter och dör efter fem felaktiga försök. Sessionen gäller i 30 dagar och bärs av kakan `klartex_session` (`httponly`, `samesite=lax`, `secure` när `BASE_URL` är https). Alla auth-svar bär `Cache-Control: no-store`.

Skrivningar med kaka kontrollerar `Origin` mot `BASE_URL`. En helt frånvarande `Origin` passerar — curl och agenter skickar ingen, och de är förstahandsanropare här.

`LOGIN_CODE_SECRET` är obligatorisk: appen vägrar starta utan den. En fallback per process skulle se ut att fungera medan den tyst knäckte varje utestående kod vid omstart, och varje kod en worker mintat åt nästa. Administratörer räknas ut ur `ADMIN_EMAILS` i stället för att vara en kolumn, så ingen registrering kan befordra sig själv.

## Felsvar från `/api/render`

Alla fel efter request-parsningen svarar med ett objekt under `detail`: alltid `type` och `message`, och `path` när felet går att peka ut i den inskickade `data`.

| `detail.type` | Status | När | `path` |
|---------------|--------|-----|--------|
| `validation_error` | 400 | Datat bryter mot mallens JSON Schema | Alltid |
| `input_error` | 400 | Blockvalidering, okänd mall, ogiltig `asset_dir` | När ett block kan pekas ut |
| `unknown_page_template` | 400 | `page_template` namnger ingen registrerad bundle | Nej |
| `token_required` | 401 | En `Authorization`-header presenterades utan `Bearer `-prefix | Nej |
| `invalid_token` | 401 | Ett token presenterades men stämmer inte | Nej |
| `token_required` | 403 | Anonymt anrop med ett `latex`-block; `block_type` namnger blocket | Alltid |
| `token_not_configured` | 503 | Ett token presenterades till en instans som saknar `API_TOKEN` | Nej |
| `overloaded` | 503 | Båda platserna upptagna, här eller i render-tjänsten (se nedan) | Nej |
| `render_error` | 500 | `xelatex` misslyckades | Nej |
| `render_unavailable` | 502 | Render-tjänsten svarade inte, svarade för långsamt, eller svarade något oanvändbart | Nej |

`502` är det enda felet som tillkommer av att kompileringen ligger i en egen tjänst. Det är alltid säkert att göra om anropet: antingen nådde det aldrig fram, eller så gick svaret förlorat. Meddelandet är generiskt och nämner varken värdnamn eller undantagstext — det som faktiskt hände loggas server-side. Alla övriga fel i tabellen ovan formuleras av kärnan och passerar oförändrade, med sin status, sin `detail` och sin `Retry-After`.

`token_required` och `503` är var för sig tvetydiga: `detail.type` ensam räcker inte, utan en klient som förgrenar på feltyp måste läsa statuskoden också. `token_required` med `401` betyder att headern inte gick att tolka och bär varken `path` eller `block_type`; med `403` betyder den att anropet var giltigt som anonymt men innehåller ett `latex`-block, och då finns båda fälten. `503` betyder antingen `overloaded` eller `token_not_configured`.

`POST`/`DELETE /api/page-templates` svarar med samma `detail`-form: `401` (`token_required` när headern saknas, `invalid_token` när tokenen är fel) och `503` (`token_not_configured`). `403` förekommer bara på `/api/render`, där anropet var giltigt som anonymt men blocket kräver mer.

`path` är en lista som adresserar den felande noden i `data`, i samma form som jsonschemas `absolute_path`: `["body", 1]` för ett block, `["body", 0, "items", 0, "text"]` för ett fält inne i ett block, `[]` för roten av `data` (t.ex. när `body` saknas). En klient kan alltså markera rätt block utan att tolka `message`, vars formuleringar ägs av klartex-kärnan.

```json
{
  "detail": {
    "type": "input_error",
    "message": "Invalid 'text' block at body[1]: 'text' is a required property",
    "path": ["body", 1]
  }
}
```

Ett request som inte ens matchar `RenderRequest` — t.ex. `data` som inte är ett objekt, eller `template` som saknas — avvisas av FastAPI med `422` och pydantics egen form på `detail` (en lista av fel), inte formen ovan.

## Belastningstak på `/api/render`

En render startar `xelatex` två gånger med 60 s timeout per körning, så en handfull samtidiga anrop räcker för att mätta en liten VM. Taket på samtidiga kompileringar sitter i render-tjänsten, som svarar `503` med `Retry-After: 5` och `detail.type = "overloaded"` i stället för att köa.

Endpointen här håller ett lika stort tak på anrop i luften och svarar likadant. Fler anrop skulle ändå bara kunna vänta på render-tjänstens `503`, och två är taket för hur många bundle-payloads som byggs i minnet samtidigt. Båda taken är per process och förutsätter **en** uvicorn-worker per container: fler workers eller repliker multiplicerar antalet.

Tidsbudgeten summerar under proxyns tak: klienten mot render-tjänsten ger upp efter som mest 5 s uppkoppling + 30 s skrivning + 130 s läsning, och Caddy väntar 180 s på svarsheadern. En klient får alltså ett strukturerat fel i stället för en avbruten uppkoppling. Edge-lagret kompletterar med rate limit och body-gräns på `POST /api/render` (se `infra/Caddyfile`), och båda containrarna har CPU-/minnes-/pids-tak i `infra/docker-compose.yml`.

## Sidmall på `/api/render`

`page_template` på toppnivå väljer sidmall och tar två former:

| Form | Betydelse |
|------|-----------|
| Sträng | Namnet på en sidmall: en bundle registrerad via `/api/page-templates`, eller den inbyggda `exempel` |
| Objekt | Kärnans slot-form, som skickas vidare som `data.page_template` |

Slot-formen är två oberoende slots, `header` och `footer`. Varje slot är `null` (tom), ett variantnamn eller ett objekt med `variant` och variantens inställningar; en utelämnad slot får ytans default. Formen ägs av kärnan och står i mallens schema (`GET /api/templates/{name}/schema`).

En bundle bär en enda `page_template.tex.jinja` som beskriver hela sidan. Den skickas till kärnan som header-slotens källa och footern sätts till `null`, vilket ger samma sida som en helsidesmall. Bundlen äger därmed båda slotarna: både `header` och `footer` i `data.page_template` får ge vika. Dokumentinställningarna där — `font`, `header_font`, `diff_style`, `page_numbers` och `first_page_header` — gäller oförändrat.

### Inbyggda sidmallar

`src/klartex_se/builtin/<namn>/` bär de sidmallar som följer med backenden: en `page_template.json` med slotarna i kärnans objektform och en beskrivning, plus de assetfiler den refererar. De löses upp med namn som bundles och listas av `GET /api/page-templates` med `"builtin": true`, men de har ingen `.tex.jinja`, kräver ingen token, och namnen är reserverade: `POST` med ett inbyggt namn och `DELETE` på det svarar `409`.

Vid `/api/render` läggs den inbyggdas `header` och `footer` över `data.page_template` — anroparens slotar får ge vika, dokumentinställningarna där (`font`, `margins`, …) gäller oförändrat — och assetsen följer med anropet som base64. Har mallens schema ett eget `logo`-fält (faktura, kvitto) tar logotypen den platsen enligt `body_logo` i definitionen och header-sloten sätts tom; annars sitter logotypen i sidhuvudet.

I dag finns en: `exempel`, demomallen för landningssidan och för den som vill se ett färdigt dokument utan egen formgivning. Logotypen är ordmärket för det fiktiva Exempelbolaget AB, satt i profilens seriff som vektorbanor (`design/exempelbolaget-ordmarke.svg` är källan), och sidfoten bär dess påhittade uppgifter.

## Assets i registrerade sidmallar

En sidmall registrerad via `/api/page-templates` sparas som en bundle: `page_template.tex.jinja` plus dess assets i samma katalog. Vid `/api/render` läses källan och alla assets härifrån och följer med anropet till render-tjänsten som base64. Där skrivs de till en temporär katalog för anropets längd, som blir både sökväg för `TEXINPUTS` och arbetskatalog för xelatex, och raderas när svaret går tillbaka. Det ger två referensformer i mallen:

| Referens i mallen | Löses mot |
|-------------------|-----------|
| `\includegraphics{logo.pdf}` | bundlens filer först, render-processens arbetskatalog som fallback |
| `\includegraphics{./logo.pdf}` | enbart bundlens filer |

Heter en fil likadant i bundlen och i render-processens arbetskatalog vinner bundlens kopia. Assets laddas upp med filnamn utan sökvägsseparatorer, så referera dem med just filnamnet — sökvägar uppåt (`../`) pekar utanför bundlen och ingår inte i kontraktet.

En bundle vars metadata listar en asset som inte finns på disk, eller vars källa inte är giltig UTF-8, går inte att skicka: anropet svarar `400 input_error` och namnger filen. Ingenting har då nått render-tjänsten.

## Databas och migrationer

Konton och parkopplingar ligger i Postgres. Adressen står i `DATABASE_URL` (`postgresql://klartex:<lösenord>@postgres:5432/klartex` i stacken); `src/klartex_se/db.py` skriver om det bara schemat till psycopg3-dialekten SQLAlchemy behöver och bygger engine och sessionsfabrik vid första användning. Ingen anslutning öppnas vid import: `/api/health` är en liveness-probe, inte en readiness-probe, och svarar `200` även när databasen är nere — annars skulle Docker starta om backenden varje gång databasen startade om.

Schemat ägs av alembic i `migrations/`. Revisionerna är handskrivna och numrerade; konventionerna står i `migrations/versions/README.md`. `alembic.ini` och `migrations/` följer med in i imagen, så deployen preflightar och migrerar med exakt den image som ska serva.

```bash
cd backend
export DATABASE_URL=postgresql://klartex:klartex@localhost:5432/klartex

alembic current        # vilken revision databasen står på (deployens preflight)
alembic heads          # vilken revision koden vill nå
alembic upgrade head
alembic downgrade -1
```

En lokal databas att köra mot:

```bash
docker run -d --name klartex-pg -p 5432:5432 \
  -e POSTGRES_USER=klartex -e POSTGRES_PASSWORD=klartex -e POSTGRES_DB=klartex \
  postgres:18-alpine
```

## Lokal utveckling

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Render-tjänsten, i ett eget skal. Kräver xelatex på PATH.
klartex serve --port 8001

# Appen, pekad på den. LOGIN_CODE_SECRET är obligatorisk — utan den startar
# den inte. BASE_URL styr sessionskakans Secure-flagga, så lokalt över http
# måste den vara http:// eller kakan aldrig skickas tillbaka.
RENDER_URL=http://localhost:8001 \
LOGIN_CODE_SECRET=dev-secret \
BASE_URL=http://localhost:8000 \
DATABASE_URL=postgresql://klartex:klartex@localhost:5432/klartex \
  uvicorn klartex_se.main:app --reload --port 8000

# Smoke-test
curl http://localhost:8000/api/templates | jq '.[].name'
curl -X POST http://localhost:8000/api/render \
  -H "Content-Type: application/json" \
  -d '{"template":"_block","data":{"lang":"sv","body":[{"type":"heading","text":"Test"}]}}' \
  -o /tmp/test.pdf
```

Utan `klartex serve` igång svarar `/api/render` `502 render_unavailable`; discovery och registret fungerar ändå.

Tester behöver ingen render-tjänst: enhetstesterna ersätter proxy-anropet, och `tests/test_contract.py` driver `klartex.server` i samma process. `xelatex` behövs bara för de två testerna som renderar på riktigt, och de hoppas över när det saknas. Samma pytest-svit körs i CI före image-bygget.

`tests/test_migrations.py` och `tests/test_accounts.py` kör mot en riktig Postgres och hoppas över när `DATABASE_URL` är osatt eller pekar på något onåbart. Bägge är destruktiva — migrationssviten börjar varje test från ett tomt `public`-schema, kontosviten tömmer kontotabellerna — så peka dem på en slaskdatabas, aldrig på en med riktiga rader. CI ger dem en engångs-servicecontainer.

`tests/conftest.py` sätter `LOGIN_CODE_SECRET` och `BASE_URL` innan appen importeras: utan den första går appen inte att importera alls, och utan den andra skulle sessionskakan bli `Secure` och aldrig skickas tillbaka över testklientens `http://testserver`.

```bash
pytest
pytest -k "not render"   # bara discovery-tester (snabbt, ingen xelatex)

DATABASE_URL=postgresql://klartex:klartex@localhost:5432/klartex \
  pytest tests/test_migrations.py tests/test_accounts.py
```

## Docker

Imagen bygger på `python:3.12-slim` och installeras ur `pyproject.toml`. Ingen TeX Live: den bor i render-imagen, som byggs på andra sidan. Ett produktrelease flyttar därmed några tiotal megabyte.

```bash
docker build -t klartex-se-backend:dev .
docker run --rm -p 8000:8000 -e RENDER_URL=http://host.docker.internal:8001 klartex-se-backend:dev
```

Hela stacken lokalt — appen mot en riktig render-tjänst — startas enklast med compose-filen i `infra/`; se `infra/README.md`.

### Kärn-pinnen

`klartex==X.Y.Z` i `pyproject.toml` är den enda platsen kärnversionen står. Render-imagen taggas med samma version (`ghcr.io/swedev/klartex-render:X.Y.Z`), så en kärnbump är att ändra pinnen, spegla den i `KLARTEX_VERSION` i `infra/.env.example` — CI felar annars — och släppa en ny appversion. Deployen skriver båda raderna till serverns `.env`, så paret rullas ut ihop.

## Deploy

App-imagen byggs av `.github/workflows/deploy.yml`, och bara när en `v*`-tagg pushas: tester, multi-arch-bygge (amd64 + arm64) till `ghcr.io/swedev/klartex-se-backend`, smoke-test av amd64-imagen mot en riktig render-container av den pinnade kärnversionen innan något publiceras, och därefter utrullning. En push till `main` bygger ingenting — `ci.yml` kör testerna och inget mer.

För produktion: bumpa `version` i `pyproject.toml` och `__version__` i `src/klartex_se/__init__.py`, merga, och pusha en matchande `v*`-tagg.
