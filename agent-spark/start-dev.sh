#!/usr/bin/env bash
# Launches one agent's Streamlit dashboard locally (not the crawl loop --
# the dashboard itself has Start/Stop buttons for that, per the
# agent-spark-core pattern; see agent-spark/core/README.md).
#
# Usage:
#   ./start-dev.sh cigna-mtsinai-negotiation
#   ./start-dev.sh animal-rights-watch
#
# Each agent runs on its own port (declared in that agent's agent.yaml) so
# multiple agents can be open side by side. Every customer entitled to a
# given agent shares that one instance -- see agent-spark/core/README.md.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
    echo "usage: $0 <agent-slug> [-- <extra streamlit args>]" >&2
    echo "available agents:" >&2
    for d in "$SCRIPT_DIR"/agents/*/; do
        [ -f "$d/dashboard.py" ] && echo "  - $(basename "$d")" >&2
    done
    exit 1
}

[ $# -ge 1 ] || usage
AGENT_SLUG="$1"
shift || true

AGENT_DIR="$SCRIPT_DIR/agents/$AGENT_SLUG"
if [ ! -f "$AGENT_DIR/dashboard.py" ]; then
    echo "error: no dashboard.py found for agent '$AGENT_SLUG' (looked in $AGENT_DIR)" >&2
    usage
fi

cd "$AGENT_DIR"

if ! command -v uv >/dev/null 2>&1; then
    echo "error: uv is not installed or not on PATH (https://docs.astral.sh/uv/)" >&2
    exit 1
fi

if [ ! -f "agent.yaml" ]; then
    echo "warning: $AGENT_DIR/agent.yaml not found -- copy agent.example.yaml and fill in" >&2
    echo "         the wiki_repo_url before starting the crawl loop." >&2
fi

if ! curl -s -m 3 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    echo "warning: ollama does not appear to be running on 127.0.0.1:11434." >&2
    echo "         start it with: ollama serve" >&2
fi

echo "Starting $AGENT_SLUG dashboard (Streamlit default port unless overridden) ..."
exec uv run streamlit run dashboard.py "$@"
