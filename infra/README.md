# infra/ — klartex.se driftsetup

Filer som beskriver hur klartex.se-stacken provisioneras och deployas på en Hetzner Cloud-server. All hosting sker idag på en enda VM med Docker Compose; allt här går att skala till fler servrar senare utan att riva ner.

## Vad ligger var

| Fil | Roll |
|-----|------|
| `provision.sh` | Skapar Hetzner-firewall + server från scratch. Idempotent. |
| `cloud-init.yaml` | Körs en gång vid första boot: installerar Docker, sätter upp användare, brandvägg, systemd-unit. |
| `docker-compose.yml` | Stackdefinition: Caddy + klartex-API. Deployas till `/srv/klartex/`. |
| `Caddyfile` | TLS + tre vhosts: `klartex.se`, `app.klartex.se`, `api.klartex.se`. Rate limit + body-gräns på `POST /render`. |
| `caddy/Dockerfile` | Caddy-image med rate limit-modulen, byggd på servern. |
| `.env.example` | Mall för `infra/.env` på servern — pinnar `BACKEND_VERSION`. |
| `../deploy/deploy.sh` | Pushar compose + Caddyfile + statiska filer till servern och reloadar. |

## Från noll till live

Förutsätter att `hcloud` CLI är autentiserad och SSH-nyckeln uppladdad (se klartex.se/CLAUDE.md).

```bash
# 1. Provisionera server
./infra/provision.sh

# 2. Vänta ~2 min, peka DNS mot returnerad IP
#    klartex.se / www / app / api  →  A-record

# 3. Konfigurera env-pinningen
cp infra/.env.example infra/.env
$EDITOR infra/.env        # bumpa BACKEND_VERSION om så önskas

# 4. Första deploy
./deploy/deploy.sh
```

## Uppgradera backend-versionen

1. Bumpa `BACKEND_VERSION` i `infra/.env`.
2. `./deploy/deploy.sh` — pullar ny image, restartar via systemd.
3. Verifiera: `curl -fsS https://api.klartex.se/templates | jq '.[].name'`.

Rollback: ändra `BACKEND_VERSION` tillbaka och kör `deploy.sh` igen. Eftersom alla version-taggar är pushade till GHCR finns alla versioner kvar att pulla.

## Caddy byggs på servern

Rate limit är inte en del av Caddy — `mholt/caddy-ratelimit` är en tredjepartsmodul som kräver en egen binär. `caddy/Dockerfile` bygger den med `xcaddy`; compose-tjänsten `caddy` har `build: ./caddy` och taggen `klartex-se-caddy:local`, som aldrig pushas till något registry. Bygget sker på servern så att arkitekturen (ARM) blir rätt utan att en image behöver versioneras i CI.

Både Caddy-versionen och modul-committen är pinnade i `caddy/Dockerfile`. Uppgradering: ändra båda `FROM caddy:<version>`-raderna till samma nya version, sätt `RATELIMIT_VERSION` till en ny tagg eller commit, och kör `deploy.sh`.

Serverkrav för bygget: utgående åtkomst till Docker Hub, GitHub och Go-modulproxyn, plus disk och RAM för Go-kompileringen (någon minut första gången; Docker cachear tills `caddy/Dockerfile` ändras).

`deploy.sh` bygger imagen och kör preflight — `caddy list-modules` (modulen finns i binären) och `caddy validate` (Caddyfilen parsar) — innan den körande stacken stoppas. Konfigen som ligger på servern säkerhetskopieras till `/srv/klartex-deploy-backup/` före rsyncen och återställs automatiskt om bygget, preflighten eller omstarten fallerar.

Startar den nya Caddyn trots preflight inte: ta bort `build:` och sätt tillbaka `image: caddy:2-alpine` i `docker-compose.yml` tillsammans med föregående Caddyfile, och kör `deploy.sh` igen. Certifikaten ligger i `./caddy-data` och påverkas inte.

## Rate limit och storleksgräns på `/render`

`POST /render` är begränsat i Caddy till 10 anrop per minut och klient-IP (IPv6 buckets per `/64`), och request-bodyn kapas vid 2 MB med `413`. Övriga endpoints — inklusive `/page-templates`, vars bundles legitimt kan vara stora — är orörda. Caddy sitter direkt mot internet utan `trusted_proxies`, så `X-Forwarded-For` kan inte kringgå taket.

Backend har dessutom ett tak på två samtidiga renders (503 + `Retry-After`), och backend-containern kör med `cpus`, `mem_limit`, `memswap_limit` och `pids_limit` satta i `docker-compose.yml` — anpassade till en cax11 (2 vCPU, 4 GB) så att OS och Caddy behåller marginal när backend är mättad.

## Tillgång till GHCR-imagen

Imagen `ghcr.io/swedev/klartex` **måste vara public** för att servern ska kunna pulla utan auth. Verifiera på:
https://github.com/orgs/swedev/packages/container/klartex/settings

Om imagen behöver vara private framöver: skapa en GHCR-PAT med `read:packages`, lägg som `GHCR_TOKEN` i `infra/.env`, lägg till `docker login ghcr.io` i `deploy.sh` innan `pull`.

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
ssh klartex@<ip> "docker compose -f /srv/klartex/docker-compose.yml ps"

# Loggar
ssh klartex@<ip> "docker compose -f /srv/klartex/docker-compose.yml logs --tail=200 klartex"
ssh klartex@<ip> "docker compose -f /srv/klartex/docker-compose.yml logs --tail=200 caddy"

# Caddy reload utan restart
ssh klartex@<ip> "docker exec caddy caddy reload --config /etc/caddy/Caddyfile"
```

## Saker som *inte* finns här (medvetet)

- **Databas.** Tillkommer i MVP fas 5 (konton/persistens).
- **Frontend-build i CI.** Görs lokalt eller i en framtida workflow; `deploy.sh` rsync:ar bara `app/dist/`.
- **Monitoring/alerting.** Hetzners egna metrics räcker tills appen lever på riktigt.
- **Backups bortom Hetzner snapshots.** Aktivera "automatic backups" på servern (+20%) när data finns.
