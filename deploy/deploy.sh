#!/usr/bin/env bash
# Push compose + Caddyfile + landing page to the server and reload the stack.
#
# Usage:  ./deploy/deploy.sh [server-host-or-ip]
# If no arg: resolves from `hcloud server ip klartex-api-1`.

set -euo pipefail

SERVER_NAME="${SERVER_NAME:-klartex-api-1}"
SSH_USER="${SSH_USER:-klartex}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# --- Resolve host -----------------------------------------------------------
if [[ $# -ge 1 ]]; then
    HOST="$1"
else
    command -v hcloud >/dev/null || { echo "hcloud not found and no host given"; exit 1; }
    HOST="$(hcloud server ip "$SERVER_NAME")"
fi
SSH="ssh -o StrictHostKeyChecking=accept-new $SSH_USER@$HOST"

echo "→ deploying to $SSH_USER@$HOST"

# --- Push infra files (compose + caddyfile + .env) --------------------------
[[ -f "$REPO_ROOT/infra/.env" ]] || { echo "infra/.env not found — copy from .env.example first"; exit 1; }

# Ensure persistent dirs exist on the server (cloud-init only runs once,
# so we don't rely on it for dirs added after initial provisioning), and
# back up the running config before rsync overwrites it. The backup lives
# outside /srv/klartex because the rsync below runs with --delete and would
# wipe a backup directory that has no local counterpart.
$SSH bash -se <<'REMOTE'
set -Eeuo pipefail
sudo mkdir -p /srv/klartex/page-templates /srv/klartex-deploy-backup
sudo chown -R klartex:klartex /srv/klartex/page-templates /srv/klartex-deploy-backup
rm -rf /srv/klartex-deploy-backup/*
for f in docker-compose.yml Caddyfile .env; do
    if [[ -f "/srv/klartex/$f" ]]; then
        cp "/srv/klartex/$f" /srv/klartex-deploy-backup/
    fi
done
if [[ -d /srv/klartex/caddy ]]; then
    cp -r /srv/klartex/caddy /srv/klartex-deploy-backup/
fi
echo "  backed up running config to /srv/klartex-deploy-backup"
REMOTE

rsync -av --delete \
    --exclude=caddy-data --exclude=caddy-config --exclude=page-templates \
    "$REPO_ROOT/infra/" "$SSH_USER@$HOST:/srv/klartex/"

# --- Push landing page (index.html, llms.txt) -------------------------------
rsync -av --delete \
    --include='index.html' --include='llms.txt' --exclude='*' \
    "$REPO_ROOT/" "$SSH_USER@$HOST:/srv/site/"

# --- Push frontend build, if present ----------------------------------------
if [[ -d "$REPO_ROOT/app/dist" ]]; then
    rsync -av --delete "$REPO_ROOT/app/dist/" "$SSH_USER@$HOST:/srv/app/"
else
    echo "  (no app/dist — skipping frontend push)"
fi

# --- Build, preflight, pull and reload --------------------------------------
$SSH bash -se <<'REMOTE'
set -Eeuo pipefail
cd /srv/klartex

# The image id behind klartex-se-caddy:local before this deploy rebuilds it.
# Empty on the first deploy, when the tag does not exist yet.
prev_caddy_image="$(docker image inspect --format '{{.Id}}' klartex-se-caddy:local 2>/dev/null || true)"
restarted=0

restore() {
    trap - ERR
    echo "✗ deploy failed — restoring config from /srv/klartex-deploy-backup"
    cp /srv/klartex-deploy-backup/docker-compose.yml \
       /srv/klartex-deploy-backup/Caddyfile \
       /srv/klartex-deploy-backup/.env /srv/klartex/
    rm -rf /srv/klartex/caddy
    if [[ -d /srv/klartex-deploy-backup/caddy ]]; then
        cp -r /srv/klartex-deploy-backup/caddy /srv/klartex/
    fi
    # A completed build has already moved klartex-se-caddy:local to the new
    # image. Restoring the old Dockerfile does not undo that — `up -d` never
    # rebuilds — so point the tag back at the image that was running, or the
    # restored Caddyfile would start on the new binary.
    if [[ -n "$prev_caddy_image" ]]; then
        docker image tag "$prev_caddy_image" klartex-se-caddy:local
    fi
    if [[ "$restarted" == 1 ]]; then
        sudo systemctl restart klartex-stack.service
    else
        echo "  stack was never stopped — running containers are untouched"
    fi
    exit 1
}
trap restore ERR

# The caddy image is built here, not pulled: `docker compose pull` alone
# would try to fetch klartex-se-caddy:local from a registry.
if docker compose pull --help | grep -q -- --ignore-buildable; then
    docker compose pull --ignore-buildable
else
    docker compose pull backend
fi

# The systemd unit runs `docker compose up -d`, which does not rebuild on a
# changed Dockerfile — build explicitly.
docker compose build --pull caddy

# Preflight the new binary and config before the running stack is stopped.
# `docker compose run` keeps the service's container_name and would collide
# with the running caddy container, so the built image is exercised directly.
docker run --rm klartex-se-caddy:local \
    caddy list-modules | grep -q 'http\.handlers\.rate_limit'
docker run --rm -v /srv/klartex/Caddyfile:/etc/caddy/Caddyfile:ro klartex-se-caddy:local \
    caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile

restarted=1
sudo systemctl restart klartex-stack.service
sleep 5
docker compose ps
running="$(docker compose ps --services --filter status=running)"
for svc in backend caddy; do
    grep -qx "$svc" <<<"$running" || {
        echo "service $svc is not running after restart"
        false
    }
done

trap - ERR
REMOTE

echo "✓ deploy complete"
