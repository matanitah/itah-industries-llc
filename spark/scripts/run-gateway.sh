#!/usr/bin/env bash
# Start the Spark gateway (bind localhost by default).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
exec uv run spark-gateway
