#!/usr/bin/env bash
# Ephemeral Cloudflare quick tunnel for local/Mac testing (URL changes each run).
set -euo pipefail
PORT="${PORT:-8080}"
exec cloudflared tunnel --url "http://127.0.0.1:${PORT}"
