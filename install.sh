#!/usr/bin/env bash
# Set up clef-mcp and (optionally) register it with Claude Code.
#
# Usage:
#   ./install.sh                          # create venv + install deps
#   CLEF_BASE_URL=http://host:11434 \
#   ./install.sh --register               # also register with `claude mcp add`
#   CLEF_BASE_URL=... CLEF_MODEL=clef-flash ./install.sh --register
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null; then
  echo "error: python3 not found" >&2
  exit 1
fi

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
.venv/bin/pip install -q -r requirements.txt
echo "venv ready: $(pwd)/.venv"

if [[ "${1:-}" == "--register" ]]; then
  if ! command -v claude >/dev/null; then
    echo "error: claude CLI not found (needed for --register)" >&2
    exit 1
  fi
  BASE_URL="${CLEF_BASE_URL:-${OLLAMA_HOST:+http://$OLLAMA_HOST}}"
  if [[ -z "${BASE_URL:-}" ]]; then
    BASE_URL="http://localhost:11434"
  fi
  echo "registering with Claude Code (base_url=$BASE_URL model=${CLEF_MODEL:-clef})"
  # Replace any previous registration (user scope preferred, fall back to local)
  claude mcp remove clef -s user >/dev/null 2>&1 || claude mcp remove clef >/dev/null 2>&1 || true
  claude mcp add clef -s user \
    -e "CLEF_BASE_URL=$BASE_URL" \
    ${CLEF_MODEL:+-e "CLEF_MODEL=$CLEF_MODEL"} \
    -- "$(pwd)/.venv/bin/python" "$(pwd)/clef_mcp.py"
  claude mcp list | grep '^clef' || true
  echo "done. Restart Claude Code (or start a new session) to load the tools."
fi
