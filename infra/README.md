# infra/ — klartex.se driftsetup

Filer som beskriver hur klartex.se-stacken provisioneras och deployas på en Hetzner Cloud-server. All hosting sker idag på en enda VM med Docker Compose; allt här går att skala till fler servrar senare utan att riva ner.

## Vad ligger var

| Fil | Roll |
|-----|------|
| `provision.sh` | Skapar Hetzner-firewall + server från scratch. Idempotent. |
| `cloud-init.yaml` | Körs en gång vid första boot: installerar Docker, sätter upp användare, brandvägg, systemd-unit. |
| `docker-compose.yml` | Stackdefinition: Caddy + klartex-API. Deployas till `/srv/klartex/`. |
| `Caddyfile` | TLS + tre vhosts: `klartex.se`, `app.klartex.se`, `api.klartex.se`. |
| `.env.example` | Mall för `infra/.env` på servern — pinnar `KLARTEX_VERSION`. |
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
$EDITOR infra/.env        # bumpa KLARTEX_VERSION om så önskas

# 4. Första deploy
./deploy/deploy.sh
```

## Uppgradera klartex-versionen

1. Bumpa `KLARTEX_VERSION` i `infra/.env`.
2. `./deploy/deploy.sh` — pullar ny image, restartar via systemd.
3. Verifiera: `curl -fsS https://api.klartex.se/templates | jq '.[].name'`.

Rollback: ändra `KLARTEX_VERSION` tillbaka och kör `deploy.sh` igen. Eftersom alla version-taggar är pushade till GHCR finns alla versioner kvar att pulla.

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
