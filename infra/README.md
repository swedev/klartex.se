# infra/ — klartex.se driftsetup

Filer som beskriver hur klartex.se-stacken provisioneras och deployas på en Hetzner Cloud-server. All hosting sker idag på en enda VM med Docker Compose; allt här går att skala till fler servrar senare utan att riva ner.

## Vad ligger var

| Fil | Roll |
|-----|------|
| `provision.sh` | Skapar Hetzner-firewall + server från scratch. Idempotent. |
| `cloud-init.yaml` | Körs en gång vid första boot: installerar Docker, sätter upp användare, brandvägg, systemd-unit. |
| `docker-compose.yml` | Stackdefinition: Caddy + backend + render + postgres. Deployas till `~/klartex/` på servern. |
| `Caddyfile` | TLS + två vhosts: `klartex.se` och `app.klartex.se`, som servar både webbappen och `/api`. Rate limit + body-gräns på `POST /api/render`. |
| `caddy/Dockerfile` | Caddy-image med rate limit-modulen, byggd på servern. |
| `.env.example` | Mall för `infra/.env` på servern — pinnar `BACKEND_VERSION` och `KLARTEX_VERSION`, bär `POSTGRES_PASSWORD`; `API_TOKEN` är valfri. |
| `../.github/workflows/deploy.yml` | Deployar vid en `v*`-tagg: syncar infra + statiska filer, bygger Caddy, preflightar, migrerar, restartar. |

Stacken har fyra containrar. `caddy` är publik entrypoint; `backend` (`../backend/`) lyssnar på loopback och bär `/api` — policy, discovery och sidmallsregistret; `render` kompilerar LaTeX åt `backend` och är nåbar enbart från den på ett internt compose-nätverk; `postgres` bär konton och parkopplingar och publicerar ingen port alls. `backend` startar först när både `render` och `postgres` är `healthy`.

`render`-imagen byggs inte här. Den är kärnans egen artefakt: `swedev/klartex` publicerar `ghcr.io/swedev/klartex-render:<kärnversion>` vid varje release, och det här repot konsumerar den.

## Från noll till live

Förutsätter att `hcloud` CLI är autentiserad och SSH-nyckeln uppladdad (se klartex.se/CLAUDE.md).

```bash
# 1. Provisionera server
./infra/provision.sh

# 2. Vänta ~2 min, peka DNS mot returnerad IP
#    klartex.se / www / app  →  A-record

# 3. Lägg env-filen på servern. Den görs en gång för hand och versionshanteras
#    aldrig — den bär POSTGRES_PASSWORD och API_TOKEN. Deployen läser den,
#    men rör aldrig annat än BACKEND_VERSION- och KLARTEX_VERSION-raderna.
#    POSTGRES_PASSWORD måste vara satt: deployen stannar innan den rör något
#    om raden saknas, och lösenordet går inte att ändra i efterhand utan att
#    databasen låses ute (det sätts en gång, när volymen initieras).
scp infra/.env.example klartex@<ip>:klartex/.env
ssh -t klartex@<ip> "nano ~/klartex/.env"

# 4. Första deploy: tagga en version vars image finns i GHCR
git tag v0.2.3 && git push origin v0.2.3
```

## En version att bumpa, en pin att följa

| | `backend` | `render` |
|---|---|---|
| Byggs av | detta repo | `swedev/klartex`, vid varje kärnrelease |
| Katalog | `backend/` | — ingen källa här |
| Image | `ghcr.io/swedev/klartex-se-backend` | `ghcr.io/swedev/klartex-render` |
| `.env` | `BACKEND_VERSION` | `KLARTEX_VERSION` |

`KLARTEX_VERSION` är ingen egen versionsserie utan en avledning: källan är `klartex==X.Y.Z` i `backend/pyproject.toml`. `ci.yml` felar om `.env.example` säger något annat, och varje backend-deploy skriver **båda** raderna till serverns `.env`. En kärnbump är därför en PR plus en tagg, utan ssh.

### Släppa en version

1. Bumpa `version` i `backend/pyproject.toml` och `__version__` i `backend/src/klartex_se/__init__.py`. Byter releasen kärna: bumpa `klartex==` i samma `pyproject.toml` och `KLARTEX_VERSION` i `.env.example` till samma värde.
2. Merga till `main`. Ingenting byggs — `ci.yml` kör testerna och pin-kontrollen.
3. Tagga samma version och pusha taggen: `git tag v0.6.1 && git push origin v0.6.1`. Taggen bygger imagen, smoke-testar den mot en riktig render-container, publicerar den och deployar, i den ordningen.
4. Verifiera: `curl -fsS https://app.klartex.se/api/health`. Deployen har redan jämfört backendens `klartex`-fält mot render-tjänstens `version`-fält och kört ett riktigt render-anrop genom `/api/render` innan den släppte återställningstrappen.

Taggen måste matcha `pyproject.toml` — annars stannar deployen innan den rör servern, eftersom image-taggen och det `/api/health` rapporterar då skulle säga olika saker.

Rollback: kör workflowen via `workflow_dispatch` från en tidigare tagg. Den checkar ut den taggens träd, läser dess version *och dess kärn-pin*, och deployar det matchande paret. Alla version-taggar ligger kvar i GHCR. Rollback stöds bara till versioner på **samma migrations-head** — se nästa avsnitt.

Kör compose-filen mot en `.env` som saknar `KLARTEX_VERSION` stannar `docker compose pull` på den saknade variabeln — före omstarten, med den körande stacken orörd.

### `API_TOKEN` i `.env` är valfri

Osatt är det mest stängda läget: vanlig rendering och discovery är öppna, `latex`-blocket svarar `403` för alla och skrivningar mot page-templates `503`. Satt låser tokenen upp båda för den som skickar den. Ingen token behöver alltså finnas på servern för att deploya — parkoppling via parla (#19) ersätter den delade tokenen, och `ADMIN_TOKEN` från `v0.4.x` kan ligga kvar eller tas bort utan att något händer.

## Databas, migrationer och dumpar

`postgres` kör `postgres:18-alpine` med data i den namngivna volymen `pgdata`. Ingen port publiceras: `backend` når den på compose-nätverket, och administration sker inifrån servern.

```bash
ssh klartex@<ip> "cd klartex && docker compose exec postgres psql -U klartex -d klartex"
```

Schemat ägs av alembic i `backend/migrations/`. Revisionerna är handskrivna och numrerade (`0001`, `0002`, …); `backend/migrations/versions/README.md` beskriver konventionerna. Migrationsmiljön följer med i app-imagen, så preflight och migration körs med exakt den image som ska serva.

### Deploy-ordningen: preflight → stop → dump → migrate → start

1. **Preflight.** `docker compose run --rm backend alembic current` mot den *nya* imagen medan den gamla stacken fortfarande servar. En image som inte kan lösa databasens aktuella revision — en rollback bakåt över en migration — felar här, innan produktionen tas ner.
2. **Stop.** `docker compose stop backend`. Ingen skrivare får finnas kvar när schemat flyttas.
3. **Dump.** `pg_dump --clean --if-exists` till `/home/klartex/db-backups/klartex-<tidsstämpel>.sql.gz` med `umask 077`. Katalogen ligger **utanför** rsync-målet `~/klartex/`, så deployens `--delete` aldrig kan röra dumparna. Filen kontrolleras (icke-tom, `gzip -t`) och de fem senaste behålls. `--clean --if-exists` för att dumpen ska gå att lägga tillbaka i den databas den ska tillbaka i: situationen den finns för är en havererad migration, där schemat redan flyttat sig.
4. **Migrate.** `docker compose run --rm backend alembic upgrade head`.
5. **Start.** `systemctl restart klartex-stack.service`, följt av hälsokontrollerna.

### Migrationerna är forward-only

Efter ett **lyckat** steg 4 startar feltrappen inte den gamla imagen igen — det vore i sig en osupportad rollback bakåt över migrationsgränsen. Deployen stannar i stället med stacken nere och skriver ut sökvägen till dumpen och kommandot nedan. Vägen framåt är en ny release som rättar felet; restore är för det som inte går att rätta framåt.

```bash
cd /home/klartex/klartex
docker compose up -d postgres

# Töm schemat först. Dumpen droppar det den själv innehåller, men en tabell
# som den havererade migrationen hann skapa står inte i den — utan det här
# steget blir resultatet en blandning av före och efter.
docker compose exec -T postgres psql -U klartex -d klartex -v ON_ERROR_STOP=1 \
  -c 'DROP SCHEMA public CASCADE; CREATE SCHEMA public;'

gunzip -c /home/klartex/db-backups/klartex-<tidsstämpel>.sql.gz \
  | docker compose exec -T postgres psql -U klartex -d klartex -v ON_ERROR_STOP=1

sudo systemctl restart klartex-stack.service
```

`ON_ERROR_STOP=1` för att `psql` annars kör vidare förbi ett fel och slutar med noll exitkod — en halvt återställd databas som ser lyckad ut. Kontrollera efteråt att `alembic current` säger den revision releasen som körde före migrationen förväntar sig.

Dumparna är en återställningspunkt för migrationen, inte en backupstrategi: de ligger på samma disk som databasen. Riktiga off-site-backups (Hetzners "automatic backups" eller en nattlig dump utanför servern) hör till när det finns kunddata.

## Caddy byggs på servern

Rate limit är inte en del av Caddy — `mholt/caddy-ratelimit` är en tredjepartsmodul som kräver en egen binär. `caddy/Dockerfile` bygger den med `xcaddy`; compose-tjänsten `caddy` har `build: ./caddy` och taggen `klartex-se-caddy:local`, som aldrig pushas till något registry. Bygget sker på servern så att arkitekturen (ARM) blir rätt utan att en image behöver versioneras i CI.

Både Caddy-versionen och modul-committen är pinnade i `caddy/Dockerfile`. Uppgradering: ändra båda `FROM caddy:<version>`-raderna till samma nya version, sätt `RATELIMIT_VERSION` till en ny tagg eller commit, och deploya med en ny version-tagg.

Serverkrav för bygget: utgående åtkomst till Docker Hub, GitHub och Go-modulproxyn, plus disk och RAM för Go-kompileringen (någon minut första gången; Docker cachear tills `caddy/Dockerfile` ändras).

Deploy-workflowen bygger imagen och kör preflight — `caddy list-modules` (modulen finns i binären) och `caddy validate` (Caddyfilen parsar) — innan den körande stacken stoppas. Konfigen som ligger på servern säkerhetskopieras till `~/deploy-backup/` före rsyncen och återställs automatiskt om bygget, preflighten eller omstarten fallerar; `klartex-se-caddy:local` pekas då tillbaka på imagen som körde. Fallerar något före omstarten rörs den körande stacken inte alls.

Startar den nya Caddyn trots preflight inte: ta bort `build:` och sätt tillbaka `image: caddy:2-alpine` i `docker-compose.yml` tillsammans med föregående Caddyfile, och deploya om. Certifikaten ligger i `./caddy-data` och påverkas inte.

## Rate limit och storleksgräns på `/api/render`

`POST /api/render` är begränsat i Caddy till 10 anrop per minut och klient-IP (IPv6 buckets per `/64`), och request-bodyn kapas vid 2 MB med `413`. Övriga endpoints — inklusive `/api/page-templates`, vars bundles legitimt kan vara stora — är orörda. Caddy sitter direkt mot internet utan `trusted_proxies`, så `X-Forwarded-For` kan inte kringgå taket.

`render` har dessutom ett tak på två samtidiga kompileringar (503 + `Retry-After`), och `backend` håller ett lika stort tak på anrop i luften dit. Alla tre containrarna kör med `cpus`, `mem_limit`, `memswap_limit` och `pids_limit` satta i `docker-compose.yml`; resursbudgeten för en cax11 (2 vCPU, 4 GB) står i kommentaren överst i den filen. `render` bär huvuddelen av minnestaket eftersom det är den som kompilerar; `backend` har 256m för de bundle-payloads den bygger, och `postgres` 512m.

Når `backend` inte `render` — nere, omstartande eller långsammare än tidsbudgeten — svarar `/api/render` `502 render_unavailable`. Tidsbudgeten summerar under proxyns tak: `xelatex` två gånger à 60 s, klienten mot `render` som mest 165 s, Caddys `response_header_timeout` 180 s.

## Tillgång till GHCR-imagerna

Båda imagerna **måste vara public** för att servern ska kunna pulla utan auth. Verifiera på:

- https://github.com/orgs/swedev/packages/container/klartex-se-backend/settings
- https://github.com/orgs/swedev/packages/container/klartex-render/settings

`klartex-render` ägs av kärnrepots release-flöde och skapas av dess första publicerande release; ett nyskapat GHCR-paket är private tills det sätts publikt för hand. Är det private stannar `docker compose pull` — före omstarten, med stacken orörd.

Om en image behöver vara private framöver: skapa en GHCR-PAT med `read:packages`, lägg som `GHCR_TOKEN` i serverns `~/klartex/.env`, och lägg till `docker login ghcr.io` i deploy-workflowens remote-block innan `pull`.

## Säkerhet

- SSH-användare `klartex` (sudoers, lösenordslös). Root-login + lösenordslogin avstängt i sshd.
- UFW släpper bara 22, 80, 443. Caddy hanterar TLS.
- `unattended-upgrades` är på för säkerhetsuppdateringar.
- `fail2ban` rebans SSH brute-force.
- `backend` lyssnar på loopback — bara Caddy kan nå den.
- `postgres` publicerar ingen port och ligger enbart på default-nätverket, inte på `render`-nätverket: anroparstyrd LaTeX kan inte ens adressera databasen. Lösenordet står i serverns `.env` och når bara `backend` och `postgres`.
- `render` publicerar ingen port alls och ligger på ett compose-nätverk med `internal: true`: den är nåbar enbart från `backend`, och har själv ingen väg ut till internet. Den har varken `environment` eller volymer, så all anroparstyrd LaTeX kompileras med både `API_TOKEN` och sidmallsregistret utom räckhåll — och det den eventuellt läser inne i containern kan inte lämna den annat än i den PDF `backend` returnerar.
- `render` kör dessutom med `no-new-privileges`, `cap_drop: ALL` och `read_only: true`; `/tmp` (asset-katalogen per anrop) och `HOME` (fontconfigs cache) är tmpfs.
- `backend` bär hemligheten och volymen men kör ingen `xelatex`. Sidmallens filer läses där och följer med anropet till `render`, som skriver dem till en temporär katalog per anrop.

## Felsökning

```bash
# Cloud-init körfärdigt?
ssh klartex@<ip> "cloud-init status"

# Stacken körs?
ssh klartex@<ip> "docker compose -f ~/klartex/docker-compose.yml ps"

# Loggar
ssh klartex@<ip> "docker compose -f ~/klartex/docker-compose.yml logs --tail=200 backend"
ssh klartex@<ip> "docker compose -f ~/klartex/docker-compose.yml logs --tail=200 render"
ssh klartex@<ip> "docker compose -f ~/klartex/docker-compose.yml logs --tail=200 caddy"

# Caddy reload utan restart
ssh klartex@<ip> "docker exec caddy caddy reload --config /etc/caddy/Caddyfile"

# Vilken kärna kör respektive tjänst? De ska vara samma.
ssh klartex@<ip> "curl -fsS http://127.0.0.1:8000/api/health"
ssh klartex@<ip> "docker compose -f ~/klartex/docker-compose.yml exec -T render \
  python3 -c \"import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health').read())\""
```

## Saker som *inte* finns här (medvetet)

- **Frontend-build och -deploy.** Källan till `app/dist` ligger på den omergade #14-grenen, inte på `main`, så en CI-utcheckning har inget att bygga och deploy-workflowen rör inte `~/app`. `app.klartex.se` servar det som senast lagts dit för hand. Hör hemma i workflowen när #14 landar.
- **Monitoring/alerting.** Hetzners egna metrics räcker tills appen lever på riktigt.
- **Backups bortom deployens dumpar.** `/home/klartex/db-backups/` är en återställningspunkt för migrationen och ligger på samma disk som databasen. Aktivera Hetzners "automatic backups" (+20%) eller lägg en nattlig dump utanför servern när det finns kunddata.
