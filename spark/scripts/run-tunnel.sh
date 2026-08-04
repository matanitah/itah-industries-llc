#!/usr/bin/env bash
# Start Cloudflare Tunnel if cloudflared + config exist.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONFIG="${CLOUDFLARED_CONFIG:-$ROOT/secrets/cloudflared.yml}"

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "cloudflared not found. Install: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"
  exit 1
fi

if [[ ! -f "$CONFIG" ]]; then
  echo "Missing tunnel config at $CONFIG"
  echo "Copy secrets/cloudflared.yml.example and add your tunnel credentials."
  exit 1
fi

exec cloudflared tunnel --config "$CONFIG" run
