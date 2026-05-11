#!/usr/bin/env bash
# Provision the klartex.se Hetzner server from scratch.
# Idempotent: re-running detects existing resources and skips them.
#
# Requires:
#   - hcloud CLI authenticated (`hcloud context active` shows klartex)
#   - SSH key already uploaded (`hcloud ssh-key list` shows it)
#   - DNS for klartex.se / app / api pointing at the resulting IP (do this AFTER)

set -euo pipefail

# --- Config -----------------------------------------------------------------
SERVER_NAME="${SERVER_NAME:-klartex-api-1}"
SERVER_TYPE="${SERVER_TYPE:-cax11}"        # ARM, 2 vCPU, 4GB, ~€3.79/mån
LOCATION="${LOCATION:-hel1}"               # Helsinki — lowest latency from SE
IMAGE="${IMAGE:-ubuntu-24.04}"
SSH_KEY_NAME="${SSH_KEY_NAME:-matte-macbookPro}"
FIREWALL_NAME="${FIREWALL_NAME:-klartex-public}"
SSH_PUBKEY_FILE="${SSH_PUBKEY_FILE:-$HOME/.ssh/id_ed25519.pub}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLOUD_INIT_SRC="$SCRIPT_DIR/cloud-init.yaml"
CLOUD_INIT_RENDERED="$(mktemp -t klartex-cloud-init.XXXXXX.yaml)"
trap 'rm -f "$CLOUD_INIT_RENDERED"' EXIT

# --- Sanity checks ----------------------------------------------------------
command -v hcloud >/dev/null || { echo "hcloud CLI not found"; exit 1; }
hcloud context active >/dev/null 2>&1 || { echo "No active hcloud context"; exit 1; }
[[ -f "$SSH_PUBKEY_FILE" ]] || { echo "SSH pubkey not found: $SSH_PUBKEY_FILE"; exit 1; }
[[ -f "$CLOUD_INIT_SRC" ]]  || { echo "cloud-init.yaml not found"; exit 1; }

# Inject local SSH pubkey into cloud-init.
SSH_PUBKEY_CONTENT="$(<"$SSH_PUBKEY_FILE")"
# Use python for safe escaping (avoid sed quoting hell).
python3 - "$CLOUD_INIT_SRC" "$SSH_PUBKEY_CONTENT" > "$CLOUD_INIT_RENDERED" <<'PY'
import sys
src, key = sys.argv[1], sys.argv[2]
sys.stdout.write(open(src).read().replace("SSH_PUBLIC_KEY_PLACEHOLDER", key.strip()))
PY

# --- Firewall ---------------------------------------------------------------
if ! hcloud firewall describe "$FIREWALL_NAME" >/dev/null 2>&1; then
    echo "→ creating firewall $FIREWALL_NAME"
    hcloud firewall create --name "$FIREWALL_NAME"
    for port in 22 80 443; do
        hcloud firewall add-rule "$FIREWALL_NAME" \
            --direction in --protocol tcp --port "$port" \
            --source-ips 0.0.0.0/0 --source-ips ::/0
    done
    # HTTP/3
    hcloud firewall add-rule "$FIREWALL_NAME" \
        --direction in --protocol udp --port 443 \
        --source-ips 0.0.0.0/0 --source-ips ::/0
else
    echo "✓ firewall $FIREWALL_NAME already exists"
fi

# --- Server -----------------------------------------------------------------
if hcloud server describe "$SERVER_NAME" >/dev/null 2>&1; then
    echo "✓ server $SERVER_NAME already exists"
else
    echo "→ creating server $SERVER_NAME ($SERVER_TYPE, $LOCATION, $IMAGE)"
    hcloud server create \
        --name        "$SERVER_NAME" \
        --type        "$SERVER_TYPE" \
        --image       "$IMAGE" \
        --location    "$LOCATION" \
        --ssh-key     "$SSH_KEY_NAME" \
        --firewall    "$FIREWALL_NAME" \
        --user-data-from-file "$CLOUD_INIT_RENDERED"
fi

# --- Summary ----------------------------------------------------------------
IP="$(hcloud server ip "$SERVER_NAME")"
cat <<EOF

────────────────────────────────────────────────────────
Server:    $SERVER_NAME ($SERVER_TYPE in $LOCATION)
IPv4:      $IP

Next steps:
  1. Point DNS:
       klartex.se      A   $IP
       www.klartex.se  A   $IP
       app.klartex.se  A   $IP
       api.klartex.se  A   $IP

  2. Wait ~2 min for cloud-init to finish, then verify:
       ssh klartex@$IP "cloud-init status --wait && docker --version"

  3. From this repo: ./deploy/deploy.sh $IP
────────────────────────────────────────────────────────
EOF
