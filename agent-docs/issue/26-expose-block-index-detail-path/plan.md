# Plan: Issue #26 — Expose the block index as a structured detail.path on validation errors

## Mål

`POST /api/render` ska ge blockvalideringsfel (kärnans `ValueError` → `detail.type = "input_error"`) ett strukturerat `detail.path` som pekar ut det felande blocket — i samma form som `detail.path` för `validation_error`-fallet (`jsonschema.ValidationError`) redan har. En klient ska kunna markera rätt block i editorn utan att regex-matcha `detail.message`, vars format ägs av kärnan.

## Triagering

> Beslutsunderlag för detta issue.

| Fält | Värde |
|------|-------|
| **Blockeras av** | Inget |
| **Blockerar** | Inget formellt — #14 (MVP fas 1, Tiptap) är konsumenten av `detail.path`, men är inte beroende av detta för att kunna mergas |
| **Relaterade issues** | #17 (stängd — där noterades behovet, och dess test `test_render_block_error_message_carries_body_index` pinnar dagens beteende), #14 (konsument), #15 (samordningsrisk, se konfliktrisk) |
| **Omfattning** | 3 filer i `backend/` (`render.py`, `tests/test_render.py`, `README.md`) |
| **Risk** | Låg |
| **Komplexitet** | Låg |
| **Säker för junior** | Ja |
| **Konfliktrisk** | Låg–medel — inga öppna planer rör `render.py`. `git diff main...origin/issue/14-fas-1-tiptap-scaffold` innehåller enbart `app/` (inga backend-filer), så #14 ger ingen mergekonflikt; dess `app/src/App.tsx` läser bara `detail.message`, ingen strängmatchning att städa. #15 (API_TOKEN) ska däremot enligt sitt issue ändra `/render`-dependencyn i `render.py`, dess tester och `backend/README.md`:s endpoint-tabell — den av #15/#26 som landar sist får en liten rebase (route-dekoratorn, testfilen, README) |

### Triagemässiga noteringar

- Ingen projekt-board-konfiguration (`agent-docs/github/info.json`/`project.json` saknas) och inga `release/*`-grenar — planen skrivs mot `main`.
- Kärnan är pinnad exakt (`klartex==0.15.0` i `backend/pyproject.toml`). Felsträngsformatet `body[i]` infördes i klartex 0.12.0 (CHANGELOG: "Valideringsfel refererar nu `body[i]`-paths") och produceras av `_validate_blocks()` i `../klartex/klartex/renderer.py`. Formatet är stabilt sedan dess, men det är ett strängkontrakt — därför måste backendens extraktion testas mot den riktiga kärnan (inte mockas) så att en framtida pin-bump som ändrar formatet slår rött.
- Faktiska felsträngar från kärnan (verifierat mot 0.15.0 i `backend/.venv`):

  | Fall | `str(e)` | `e.__cause__` |
  |------|----------|---------------|
  | Saknat fält i toppnivåblock | `Invalid 'text' block at body[1]: 'text' is a required property` | `ValidationError`, `absolute_path = []` |
  | Fel fälttyp inne i block | `Invalid 'heading' block at body[0]: 123 is not of type 'string'` | `ValidationError`, `absolute_path = ['text']` |
  | Fel djupt inne i block | `Invalid 'list' block at body[0]: 5 is not of type 'string'` | `ValidationError`, `absolute_path = ['items', 0, 'text']` |
  | Nästlat block (`columns`) | `Invalid 'text' block at body[0].items[1][0]: 'text' is a required property` | `ValidationError`, `absolute_path = []` |
  | Okänd blocktyp | `Unknown block type 'nope' at body[0]. Available: agenda, …` | `None` |
  | Block utan `type` | `Block at body[i] is missing 'type'` — i praktiken onåbart via API:t: toppnivåschemat kräver `type` (ger `validation_error` med `path = ['body', i]`) och nästlade carriers avvisar okända fält via förälderns schema | `None` |
  | Okänd mall, ogiltig `asset_dir` | Ingen blockposition i strängen | — |

  Observera att `Block at body[1] is missing 'type'` i dag når klienten som `validation_error` med `path = ["body", 1]` — den vägen är redan strukturerad och rörs inte. Detsamma gäller saknad `body` (`validation_error`, `path = []` = roten av `data`) och `body` som inte är en array (`path = ["body"]`): toppnivåschemat fångar dem innan `_validate_blocks()` körs. Kärnans `ValueError("Block engine data must include a 'body' array")` i `block_engine.py` är därmed onåbar via API:t.

## Angreppssätt

Issuets förslag (användarbeslut, från issue-texten) är att **backend** extraherar blockindexet och exponerar det som `detail.path`. Alternativet — att kärnan kastar en strukturerad exception med `.path` — vore renare men kräver kärn-release plus pin-bump och ligger utanför issuets scope; se designbeslut 1.

Extraktionen görs i en liten hjälpfunktion i `render.py` som matchar de **tre exakta meddelandeformerna** `_validate_blocks()` producerar (inte en lös sökning efter `at body[...]`), och bygger en path-lista av samma slag som `list(e.absolute_path)` ger för `validation_error`: `["body", 1]`, `["body", 0, "items", 1, 0]`. När `ValueError` har ett `jsonschema.ValidationError` som `__cause__` (fallet "Invalid '<typ>' block") läggs dess `absolute_path` — positionen *inne i* blocket — på efter blockpositionen, så att t.ex. fel fälttyp i `body[0].items[0].text` blir `["body", 0, "items", 0, "text"]`. Det gör de två felvägarna ekvivalenta för klienten: `path` adresserar alltid den felande noden i den inskickade `data`.

Prototyp (körd mot kärnan i `backend/.venv`, alla fall ovan ger förväntad path; injektionsfallet med en blocktyp som själv innehåller `' at body[9]. Available: ` ger korrekt `["body", 0]` tack vare att det girigt matchade `'.*'` fångar hela typnamnet):

```python
_WHERE = r"body(?:\[\d+\]|\.[a-z_]+)+"
_BLOCK_ERROR_RE = re.compile(
    rf"^(?:Block at (?P<a>{_WHERE}) is missing 'type'$"
    rf"|Unknown block type '.*' at (?P<b>{_WHERE})\. Available: "
    rf"|Invalid '[a-z_]+' block at (?P<c>{_WHERE}): )",
    re.DOTALL,
)

def _block_error_path(exc: ValueError) -> list[str | int] | None:
    """Locate the block a klartex block-validation error refers to."""
    m = _BLOCK_ERROR_RE.match(str(exc))
    if not m:
        return None
    where = m.group("a") or m.group("b") or m.group("c")
    path = [int(s) if s.isdigit() else s for s in re.findall(r"\d+|[a-z_]+", where)]
    cause = exc.__cause__
    if isinstance(cause, ValidationError):
        path.extend(cause.absolute_path)
    return path
```

`type` förblir `"input_error"` (ingen brytande ändring för klienter som redan dispatchar på typen); `path` läggs till **bara** när en blockposition finns. Övriga `ValueError` (okänd mall, ogiltig `asset_dir`) svarar exakt som i dag.

## Steg

### Fas 1: Extraktion i backend

1. Lägg till hjälpfunktionen `_block_error_path()` + regexen ovan i `render.py`, med kort kodkommentar som anger att formerna kommer från `klartex.renderer._validate_blocks` och pinnas av testerna i `test_render.py` (tekniskt constraint, inget produktresonemang)
   - Filer att ändra: `backend/src/klartex_se/render.py`
2. I `except ValueError`-grenen: bygg `detail = {"type": "input_error", "message": str(e)}` och sätt `detail["path"] = path` när `_block_error_path(e)` inte är `None`
   - Filer att ändra: `backend/src/klartex_se/render.py`
3. Uppdatera modulens docstring ("Validation errors … are mapped to HTTP responses with structured detail") och `responses[400]`-beskrivningen så att OpenAPI-texten nämner `detail.path`. Det är prosa i OpenAPI-dokumentet, inte ett testat kontrakt — `test_openapi_schema_is_served` kontrollerar bara att `/api/render` finns; kontraktet pinnas av endpoint-testerna i Fas 2, och en response-modell för `detail` ligger utanför #26
   - Filer att ändra: `backend/src/klartex_se/render.py`

### Fas 2: Tester

1. Skriv om `test_render_block_error_message_carries_body_index` (som i dag asserterar `"path" not in detail`) till att assertera `detail["path"] == ["body", 1]` respektive `["body", 0]`, och behåll `"body[1]" in detail["message"]` — meddelandet ska fortsatt vara läsbart. Uppdatera i samma veva `test_render_validation_error_returns_structured_400` (rad 43), vars kommentar beskriver blockfel som enbart meddelande: lägg till `detail["path"] == ["body", 0]` och skriv om kommentaren, eller slå ihop de två testerna till ett
   - Filer att ändra: `backend/tests/test_render.py`
2. Nya endpoint-tester mot den riktiga kärnan (inga mocks, ingen xelatex behövs — valideringen sker före kompilering):
   - nästlat block i `columns` **med** fel fälttyp (`items[1][0] = {"type": "text", "text": 123}`) → `path == ["body", 0, "items", 1, 0, "text"]` — täcker sammansättningen blockposition + `__cause__.absolute_path` i ett fall
   - fel fälttyp i toppnivåblock (`{"type": "heading", "text": 123}`) → `path == ["body", 0, "text"]`
   - djupt fält (`list.items[0].text`) → `path == ["body", 0, "items", 0, "text"]`
   - okänd blocktyp → `path == ["body", 0]`; variant där typnamnet själv innehåller `' at body[9]. Available: ` → fortfarande `["body", 0]`
   - okänd mall (`template: "nope"`) → `input_error` **utan** `path`-nyckel
   - `validation_error`-fallet (`{"body": [{"text": "x"}]}` utan `type`) → oförändrat `path == ["body", 0]` — bevisar att de två vägarna ger samma form
   - Filer att ändra: `backend/tests/test_render.py`
3. Enhetstester direkt på `_block_error_path()` för det onåbara formatet `Block at body[2].content[0] is missing 'type'` → `["body", 2, "content", 0]`, samt för en `ValueError` utan match → `None`
   - Filer att ändra: `backend/tests/test_render.py`

### Fas 3: Dokumentation

1. Nytt avsnitt i `backend/README.md`, efter "Endpoints" (t.ex. "Felsvar från `/api/render`"): tabell över `detail.type` (`validation_error`, `input_error`, `unknown_page_template`, `overloaded`, `render_error`), att `path` finns för `validation_error` alltid (kan vara `[]` = roten av `data`, t.ex. saknad `body`) och för `input_error` när ett block kan pekas ut, path-formen (`["body", 1, "items", 0, "text"]`) och ett kort JSON-exempel. Avgränsa tabellen till svar efter request-parsning: ett request som inte matchar `RenderRequest` (t.ex. `data` som inte är ett objekt) ger FastAPI:s egen 422 med pydantic-formen på `detail` (en lista), inte den här formen — nämn det i en rad
   - Filer att ändra: `backend/README.md`
2. I PR-bodyn: notera att #14-grenens `App.tsx` kan börja använda `detail.path` för blockmarkering och inte ska matcha på `detail.message`; `Closes #26`

## Filöversikt

| Fil | Åtgärd | Syfte |
|-----|--------|-------|
| `backend/src/klartex_se/render.py` | Ändra | `_block_error_path()` + regex; `path` i `input_error`-detail när blockposition finns; docstring/OpenAPI-text |
| `backend/tests/test_render.py` | Ändra | Skriv om det befintliga `body[i]`-testet; nya tester för nästlade block, fält-path, injektion, icke-blockfel utan `path`, likformighet med `validation_error`; enhetstester på hjälpfunktionen |
| `backend/README.md` | Ändra | Avsnitt om felsvar från `/api/render` med `detail.type`/`detail.path`-kontraktet |

## Berörda kodområden

Lista de primära kataloger/områden som planen berör (för konfliktdetektering):
- `backend/src/klartex_se/` (`render.py`)
- `backend/tests/` (`test_render.py`)
- `backend/` (README)

## Designbeslut

> Icke-triviala val gjorda under planeringen. Feedback välkommen; annars implementeras enligt dessa.

### 1. Extraktion i backend, inte strukturerad exception i kärnan
**Alternativ:** A) backend parsar kärnans felsträng bakom en pinnad, testad regex; B) kärnan får en `BlockValidationError(ValueError)` med `.path`, backend läser attributet
**Beslut:** A
**Motivering:** Issuet föreslår uttryckligen A ("extract the block index and expose it as `detail.path`") — användarbeslut. B är arkitektoniskt renare och i linje med CLAUDE.md:s princip att kärnbehov löses i kärnan, men kräver kärn-release + pin-bump och blockerar #14:s felmarkering på en extern leverans. A ger värdet nu och kan bytas till B utan att API-kontraktet mot klienten ändras (samma `path`). Om B önskas senare är det ett eget issue i `swedev/klartex`; planen skapar inget sådant på eget bevåg.

### 2. `type` förblir `"input_error"`; `path` läggs till som nytt fält
**Alternativ:** A) behåll `type`, lägg till `path`; B) ny `type: "block_error"` för fel med path; C) döp om till `validation_error` så att båda vägarna får samma `type`
**Beslut:** A — agentens egen bedömning, öppen att ifrågasätta
**Motivering:** A är rent additiv: befintliga klienter (och `test_render_unknown_template_returns_400`) fortsätter fungera. Klienten avgör "finns ett block att markera?" via `path`-fältets närvaro, inte via `type`. C skulle sudda ut skillnaden mellan schemafel (jsonschema) och kärnans övriga `ValueError` (okänd mall) utan att ge klienten något.

### 3. Path-form: samma som `validation_error`, blockposition + position inne i blocket
**Alternativ:** A) `path` = lista `str | int` som `list(e.absolute_path)`, blockets position följd av `__cause__.absolute_path`; B) bara blockets position (`["body", 1]`); C) råsträngen `"body[1].items[0]"`
**Beslut:** A — agentens egen bedömning, öppen att ifrågasätta
**Motivering:** Issuets mål är att båda felvägarna ska se likadana ut; `validation_error` ger redan `["body", 1]`/`["lang"]`, så listformen är etablerad konvention i `render.py`. Att lägga på `__cause__.absolute_path` kostar en rad och gör att fel i ett fält (`body[0].items[0].text`) blir adresserbart precis som via jsonschema-vägen. B är minsta möjliga tolkning av issuet men lämnar fältnivån åt strängen. C vore en ny form att parsa.

### 4. Regexen matchar de tre exakta meddelandeformerna, inte första `at body[...]`
**Alternativ:** A) alternation ankrad på `^Block at …`, `^Unknown block type '.*' at …\. Available: `, `^Invalid '[a-z_]+' block at …: `; B) `re.search(r"at (body\S+)")`
**Beslut:** A — agentens egen bedömning
**Motivering:** I "Unknown block type"-meddelandet är typnamnet användarstyrt och kan innehålla `at body[9]`; B skulle då peka fel. A:s giriga `'.*'` tillsammans med ankaret `\. Available: ` väljer sista förekomsten. I "Invalid"-formen är typnamnet redan validerat mot `KNOWN_BLOCK_TYPES` (`[a-z_]+`). Priset är att ett nytt meddelandeformat i kärnan ger `path` = saknas i stället för fel path — och testerna mot den riktiga kärnan fångar det vid nästa pin-bump.

### 5. `path` utelämnas (inte `null`) när ingen blockposition finns
**Alternativ:** A) nyckeln saknas; B) `path: null`
**Beslut:** A — agentens egen bedömning, öppen att ifrågasätta
**Motivering:** Payloaden för icke-blockfel blir byte-identisk med i dag. Klientkoden (`if (detail.path)`) är densamma i båda fallen.

### 6. Ingen versionsbump i PR:en
**Alternativ:** A) bumpa `0.4.2` → `0.4.3`/`0.5.0` i PR:en; B) lämna versionen — release-committen ("Release 0.x.y") bumpar när ändringen taggas
**Beslut:** B — agentens egen bedömning
**Motivering:** De senaste releaserna (0.4.1, 0.4.2) bumpades i separata release-commits, inte i feature-PR:erna, och `deploy.yml` bygger bara på `v*`-taggar. Att bumpa här skulle bara skapa konflikt med nästa release-commit.

## Verifieringschecklista

- [ ] `cd backend && .venv/bin/python -m pytest -rs` grönt; render-testerna körs (inte skippade)
- [ ] `POST /api/render` med `{"template": "_block", "data": {"body": [{"type": "heading", "text": "ok"}, {"type": "text"}]}}` → 400, `detail.type == "input_error"`, `detail.path == ["body", 1]`, `detail.message` innehåller fortfarande `body[1]`
- [ ] Nästlat block i `columns` med fel fälttyp → `path == ["body", 0, "items", 1, 0, "text"]`; utan fältfel (saknat `text`) → `["body", 0, "items", 1, 0]`
- [ ] Fel fälttyp i block → `path == ["body", 0, "text"]`; djupt fält → `["body", 0, "items", 0, "text"]`
- [ ] Okänd blocktyp, inklusive typnamn som innehåller `' at body[9]. Available: ` → `path == ["body", 0]`
- [ ] Okänd mall (`template: "nope"`) → `input_error` utan `path`-nyckel (oförändrad payload)
- [ ] `validation_error`-vägen oförändrad: `{"body": [{"text": "x"}]}` → `path == ["body", 0]`; `{}` → `path == []`
- [ ] `test_render_validation_error_returns_structured_400` uppdaterat (asserterar `path`, kommentaren beskriver inte längre blockfel som enbart meddelande)
- [ ] `render_error` (500), `overloaded` (503), `unknown_page_template` (400) oförändrade
- [ ] `/api/openapi.json` genereras utan fel efter docstring-/responses-ändringen (`test_discovery.py`); 400-beskrivningen nämner `detail.path`
- [ ] `backend/README.md` beskriver `detail.type`/`detail.path`-kontraktet
- [ ] PR-bodyn: `Closes #26`, notis till #14 om att använda `detail.path`, notis om rebase-behovet mot #15 om den landar först
