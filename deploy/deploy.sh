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

rsync -av --delete \
    --exclude=caddy-data --exclude=caddy-config \
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

# --- Pull new image and reload ----------------------------------------------
$SSH bash -se <<'REMOTE'
set -euo pipefail
cd /srv/klartex
docker compose pull
sudo systemctl restart klartex-stack.service
sleep 3
docker compose ps
REMOTE

echo "✓ deploy complete"
