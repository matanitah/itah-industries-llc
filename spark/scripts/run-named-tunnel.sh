#!/usr/bin/env bash
# Run the named Cloudflare Tunnel (stable hostnames for matanitah.com).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONFIG="${CLOUDFLARED_CONFIG:-$ROOT/secrets/cloudflared.named.yml}"

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "Install cloudflared first (brew install cloudflare/cloudflare/cloudflared)"
  exit 1
fi

if [[ ! -f "$CONFIG" ]]; then
  echo "Missing $CONFIG"
  echo "Copy secrets/cloudflared.named.yml.example → secrets/cloudflared.named.yml and fill tunnel UUID + credentials path."
  exit 1
fi

if grep -q 'REPLACE_WITH' "$CONFIG"; then
  echo "Edit $CONFIG and replace REPLACE_WITH_* placeholders first."
  exit 1
fi

exec cloudflared tunnel --config "$CONFIG" run
