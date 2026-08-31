# infra/ — klartex.se driftsetup

Filer som beskriver hur klartex.se-stacken provisioneras och deployas på en Hetzner Cloud-server. All hosting sker idag på en enda VM med Docker Compose; allt här går att skala till fler servrar senare utan att riva ner.

## Vad ligger var

| Fil | Roll |
|-----|------|
| `provision.sh` | Skapar Hetzner-firewall + server från scratch. Idempotent. |
| `cloud-init.yaml` | Körs en gång vid första boot: installerar Docker, sätter upp användare, brandvägg, systemd-unit. |
| `docker-compose.yml` | Stackdefinition: Caddy + backend + render. Deployas till `~/klartex/` på servern. |
| `Caddyfile` | TLS + två vhosts: `klartex.se` och `app.klartex.se`, som servar både webbappen och `/api`. Rate limit + body-gräns på `POST /api/render`. |
| `caddy/Dockerfile` | Caddy-image med rate limit-modulen, byggd på servern. |
| `.env.example` | Mall för `infra/.env` på servern — pinnar `BACKEND_VERSION` och `KLARTEX_VERSION`; `API_TOKEN` är valfri. |
| `../.github/workflows/deploy.yml` | Deployar vid en `v*`-tagg: syncar infra + statiska filer, bygger Caddy, preflightar, restartar. |

Stacken har tre containrar. `caddy` är publik entrypoint; `backend` (`../backend/`) lyssnar på loopback och bär `/api` — policy, discovery och sidmallsregistret; `render` kompilerar LaTeX åt `backend` och är nåbar enbart från den på ett internt compose-nätverk. `backend` startar först när `render` är `healthy`.

`render`-imagen byggs inte här. Den är kärnans egen artefakt: `swedev/klartex` publicerar `ghcr.io/swedev/klartex-render:<kärnversion>` vid varje release, och det här repot konsumerar den.

## Från noll till live

Förutsätter att `hcloud` CLI är autentiserad och SSH-nyckeln uppladdad (se klartex.se/CLAUDE.md).

```bash
# 1. Provisionera server
./infra/provision.sh

# 2. Vänta ~2 min, peka DNS mot returnerad IP
#    klartex.se / www / app  →  A-record

# 3. Lägg env-filen på servern. Den görs en gång för hand och versionshanteras
#    aldrig — den bär API_TOKEN. Deployen läser den, men rör aldrig annat än
#    BACKEND_VERSION- och KLARTEX_VERSION-raderna.
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

Rollback: kör workflowen via `workflow_dispatch` från en tidigare tagg. Den checkar ut den taggens träd, läser dess version *och dess kärn-pin*, och deployar det matchande paret. Alla version-taggar ligger kvar i GHCR.

Kör compose-filen mot en `.env` som saknar `KLARTEX_VERSION` stannar `docker compose pull` på den saknade variabeln — före omstarten, med den körande stacken orörd.

### `API_TOKEN` i `.env` är valfri

Osatt är det mest stängda läget: vanlig rendering och discovery är öppna, `latex`-blocket svarar `403` för alla och skrivningar mot page-templates `503`. Satt låser tokenen upp båda för den som skickar den. Ingen token behöver alltså finnas på servern för att deploya — parkoppling via parla (#19) ersätter den delade tokenen, och `ADMIN_TOKEN` från `v0.4.x` kan ligga kvar eller tas bort utan att något händer.

## Caddy byggs på servern

Rate limit är inte en del av Caddy — `mholt/caddy-ratelimit` är en tredjepartsmodul som kräver en egen binär. `caddy/Dockerfile` bygger den med `xcaddy`; compose-tjänsten `caddy` har `build: ./caddy` och taggen `klartex-se-caddy:local`, som aldrig pushas till något registry. Bygget sker på servern så att arkitekturen (ARM) blir rätt utan att en image behöver versioneras i CI.

Både Caddy-versionen och modul-committen är pinnade i `caddy/Dockerfile`. Uppgradering: ändra båda `FROM caddy:<version>`-raderna till samma nya version, sätt `RATELIMIT_VERSION` till en ny tagg eller commit, och deploya med en ny version-tagg.

Serverkrav för bygget: utgående åtkomst till Docker Hub, GitHub och Go-modulproxyn, plus disk och RAM för Go-kompileringen (någon minut första gången; Docker cachear tills `caddy/Dockerfile` ändras).

Deploy-workflowen bygger imagen och kör preflight — `caddy list-modules` (modulen finns i binären) och `caddy validate` (Caddyfilen parsar) — innan den körande stacken stoppas. Konfigen som ligger på servern säkerhetskopieras till `~/deploy-backup/` före rsyncen och återställs automatiskt om bygget, preflighten eller omstarten fallerar; `klartex-se-caddy:local` pekas då tillbaka på imagen som körde. Fallerar något före omstarten rörs den körande stacken inte alls.

Startar den nya Caddyn trots preflight inte: ta bort `build:` och sätt tillbaka `image: caddy:2-alpine` i `docker-compose.yml` tillsammans med föregående Caddyfile, och deploya om. Certifikaten ligger i `./caddy-data` och påverkas inte.

## Rate limit och storleksgräns på `/api/render`

`POST /api/render` är begränsat i Caddy till 10 anrop per minut och klient-IP (IPv6 buckets per `/64`), och request-bodyn kapas vid 2 MB med `413`. Övriga endpoints — inklusive `/api/page-templates`, vars bundles legitimt kan vara stora — är orörda. Caddy sitter direkt mot internet utan `trusted_proxies`, så `X-Forwarded-For` kan inte kringgå taket.

`render` har dessutom ett tak på två samtidiga kompileringar (503 + `Retry-After`), och `backend` håller ett lika stort tak på anrop i luften dit. Båda containrarna kör med `cpus`, `mem_limit`, `memswap_limit` och `pids_limit` satta i `docker-compose.yml`; resursbudgeten för en cax11 (2 vCPU, 4 GB) står i kommentaren överst i den filen. `render` bär huvuddelen av minnestaket eftersom det är den som kompilerar; `backend` behöver sina 768m för de bundle-payloads den bygger.

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

- **Databas.** Tillkommer i MVP fas 5 (konton/persistens).
- **Frontend-build och -deploy.** Källan till `app/dist` ligger på den omergade #14-grenen, inte på `main`, så en CI-utcheckning har inget att bygga och deploy-workflowen rör inte `~/app`. `app.klartex.se` servar det som senast lagts dit för hand. Hör hemma i workflowen när #14 landar.
- **Monitoring/alerting.** Hetzners egna metrics räcker tills appen lever på riktigt.
- **Backups bortom Hetzner snapshots.** Aktivera "automatic backups" på servern (+20%) när data finns.
