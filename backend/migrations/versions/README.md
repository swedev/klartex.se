# migrations/versions/

Alembic-revisioner, en fil per revision.

## Konventioner

- **Numrerade revisions-id:n**, `0001`, `0002`, … i filnamnet tillsammans med
  en kort beskrivning: `0001_accounts.py`. `revision`/`down_revision` bär
  samma nummer som strängar, så historiken går att läsa utan att öppna
  filerna. Samma form som styrlas `migrations/versions/`.
- **Handskrivna.** Autogenerate används inte; `env.py` har därför inget
  `target_metadata`. En revision skriver sin DDL med `op.execute()` eller
  alembics `op`-API.
- **`downgrade()` är definierad**, inte `pass`. Deployen är forward-only i
  produktion, men migrationstesterna kör ner och upp igen, och en
  odefinierad nedväg gör revisionen otestbar.
- **DDL som kommer från ett paket fryses här, den importeras inte.**
  `parla.schema.PROVIDER_SQL` kopieras ordagrant in i revisionen med den
  commit den kopierades från angiven i docstringen. Migrationshistoriken
  tillhör klartex: ett paketbump får inte tyst ändra vad en färsk databas
  får. En ändring uppströms kommer som en egen revision.
