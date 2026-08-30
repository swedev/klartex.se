# infra/ — klartex.se driftsetup

Filer som beskriver hur klartex.se-stacken provisioneras och deployas på en Hetzner Cloud-server. All hosting sker idag på en enda VM med Docker Compose; allt här går att skala till fler servrar senare utan att riva ner.

## Vad ligger var

| Fil | Roll |
|-----|------|
| `provision.sh` | Skapar Hetzner-firewall + server från scratch. Idempotent. |
| `cloud-init.yaml` | Körs en gång vid första boot: installerar Docker, sätter upp användare, brandvägg, systemd-unit. |
| `docker-compose.yml` | Stackdefinition: Caddy + klartex-backend. Deployas till `~/klartex/` på servern. |
| `Caddyfile` | TLS + två vhosts: `klartex.se` och `app.klartex.se`, som servar både webbappen och `/api`. Rate limit + body-gräns på `POST /api/render`. |
| `caddy/Dockerfile` | Caddy-image med rate limit-modulen, byggd på servern. |
| `.env.example` | Mall för `infra/.env` på servern — pinnar `BACKEND_VERSION`; `API_TOKEN` är valfri. |
| `../.github/workflows/deploy.yml` | Deployar vid en `v*`-tagg: syncar infra + statiska filer, bygger Caddy, preflightar, restartar. |

## Från noll till live

Förutsätter att `hcloud` CLI är autentiserad och SSH-nyckeln uppladdad (se klartex.se/CLAUDE.md).

```bash
# 1. Provisionera server
./infra/provision.sh

# 2. Vänta ~2 min, peka DNS mot returnerad IP
#    klartex.se / www / app  →  A-record

# 3. Lägg env-filen på servern. Den görs en gång för hand och versionshanteras
#    aldrig — den bär API_TOKEN. Deployen läser den, men rör aldrig annat än
#    BACKEND_VERSION-raden.
scp infra/.env.example klartex@<ip>:klartex/.env
ssh -t klartex@<ip> "nano ~/klartex/.env"

# 4. Första deploy: tagga en version vars image finns i GHCR
git tag v0.2.3 && git push origin v0.2.3
```

## Uppgradera backend-versionen

1. Bumpa `version` i `backend/pyproject.toml` och `__version__` i `backend/src/klartex_se/__init__.py`.
2. Merga till `main`. Ingenting byggs — `ci.yml` kör bara testerna.
3. Tagga samma version och pusha taggen: `git tag v0.2.4 && git push origin v0.2.4`. Taggen bygger imagen, smoke-testar den, publicerar den och deployar, i den ordningen.
4. Verifiera: `curl -fsS https://app.klartex.se/api/health`.

Taggen måste matcha `pyproject.toml` — annars stannar deployen innan den rör servern, eftersom image-taggen och det `/api/health` rapporterar då skulle säga olika saker.

Rollback: kör workflowen via `workflow_dispatch` från en tidigare tagg. Den checkar ut den taggens träd, läser dess version och deployar den imagen. Alla version-taggar ligger kvar i GHCR.

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

Backend har dessutom ett tak på två samtidiga renders (503 + `Retry-After`), och backend-containern kör med `cpus`, `mem_limit`, `memswap_limit` och `pids_limit` satta i `docker-compose.yml` — anpassade till en cax11 (2 vCPU, 4 GB) så att OS och Caddy behåller marginal när backend är mättad.

## Tillgång till GHCR-imagen

Imagen `ghcr.io/swedev/klartex-se-backend` **måste vara public** för att servern ska kunna pulla utan auth. Verifiera på:
https://github.com/orgs/swedev/packages/container/klartex-se-backend/settings

Om imagen behöver vara private framöver: skapa en GHCR-PAT med `read:packages`, lägg som `GHCR_TOKEN` i serverns `~/klartex/.env`, och lägg till `docker login ghcr.io` i deploy-workflowens remote-block innan `pull`.

## Säkerhet

- SSH-användare `klartex` (sudoers, lösenordslös). Root-login + lösenordslogin avstängt i sshd.
- UFW släpper bara 22, 80, 443. Caddy hanterar TLS.
- `unattended-upgrades` är på för säkerhetsuppdateringar.
- `fail2ban` rebans SSH brute-force.
- Klartex-containern lyssnar på loopback — bara Caddy kan nå den.

## Felsökning

```bash
# Cloud-init körfärdigt?
ssh klartex@<ip> "cloud-init status"

# Stacken körs?
ssh klartex@<ip> "docker compose -f ~/klartex/docker-compose.yml ps"

# Loggar
ssh klartex@<ip> "docker compose -f ~/klartex/docker-compose.yml logs --tail=200 klartex"
ssh klartex@<ip> "docker compose -f ~/klartex/docker-compose.yml logs --tail=200 caddy"

# Caddy reload utan restart
ssh klartex@<ip> "docker exec caddy caddy reload --config /etc/caddy/Caddyfile"
```

## Saker som *inte* finns här (medvetet)

- **Databas.** Tillkommer i MVP fas 5 (konton/persistens).
- **Frontend-build och -deploy.** Källan till `app/dist` ligger på den omergade #14-grenen, inte på `main`, så en CI-utcheckning har inget att bygga och deploy-workflowen rör inte `~/app`. `app.klartex.se` servar det som senast lagts dit för hand. Hör hemma i workflowen när #14 landar.
- **Monitoring/alerting.** Hetzners egna metrics räcker tills appen lever på riktigt.
- **Backups bortom Hetzner snapshots.** Aktivera "automatic backups" på servern (+20%) när data finns.
