#!/usr/bin/env bash
# Run the whole app for local development (macOS / Linux): Django API on :8000
# and the Vite dev server on :5173, side by side, with one Ctrl+C taking both
# down. Open http://localhost:5173 to use the app. Windows users: scripts/dev.ps1.
#
# On a clean machine this installs what's missing and skips what's present:
#   mise (the project's tool manager) -> uv + node; uv -> Python 3.13.
# If uv and npm are already on PATH it uses them directly and never touches mise.
#
# Usage: bash scripts/dev.sh
# Env:   BACKEND_PORT (8000), FRONTEND_PORT (5173)

# No `set -u`: macOS ships bash 3.2, where expanding an empty array under -u
# errors. -e + pipefail are enough here.
set -eo pipefail
cd "$(dirname "$0")/.."

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

# On Apple Silicon the models run on the MPS (Metal) GPU; let any op that MPS
# lacks fall back to CPU instead of raising. Harmless on Linux. Set
# AEA_DEVICE=cpu to force CPU everywhere if MPS ever misbehaves.
export PYTORCH_ENABLE_MPS_FALLBACK="${PYTORCH_ENABLE_MPS_FALLBACK:-1}"

# ── Toolchain: use uv + npm directly if present, otherwise manage via mise ──
PREFIX=()
if command -v uv >/dev/null 2>&1 && command -v npm >/dev/null 2>&1; then
  :
else
  MISE="$(command -v mise || true)"
  if [[ -z "$MISE" && -x "$HOME/.local/bin/mise" ]]; then
    MISE="$HOME/.local/bin/mise"
  fi
  if [[ -z "$MISE" ]]; then
    echo "==> Installing mise (https://mise.run)"
    if command -v curl >/dev/null 2>&1; then
      curl -fsSL https://mise.run | sh
    elif command -v wget >/dev/null 2>&1; then
      wget -qO- https://mise.run | sh
    else
      echo "error: need curl or wget to install mise" >&2
      exit 1
    fi
    MISE="$HOME/.local/bin/mise"
  fi
  [[ -x "$MISE" ]] || { echo "error: mise not found after install" >&2; exit 1; }
  echo "==> Ensuring uv + node via mise (mise install)"
  "$MISE" install
  PREFIX=("$MISE" exec --)
fi

# ── Dependencies ───────────────────────────────────────────────────────────
echo "==> Syncing Python dependencies (uv sync)"
"${PREFIX[@]}" uv sync
if [[ ! -d frontend/node_modules ]]; then
  echo "==> Installing frontend dependencies (npm install)"
  ( cd frontend && exec "${PREFIX[@]}" npm install )
fi
echo "==> Applying database migrations"
"${PREFIX[@]}" uv run python manage.py migrate

# ── Run both servers; kill the whole tree on exit ───────────────────────────
# `set -m` puts each background job in its own process group, so killing the
# negative PID tears down the whole tree (Django's reloader child, Vite's node
# child) instead of orphaning it.
set -m

# 127.0.0.1 (not 0.0.0.0) so macOS doesn't pop the "accept incoming
# connections" firewall prompt on every start.
"${PREFIX[@]}" uv run python manage.py runserver "127.0.0.1:${BACKEND_PORT}" &
backend=$!
( cd frontend && exec "${PREFIX[@]}" npm run dev -- --port "${FRONTEND_PORT}" ) &
frontend=$!

cleanup() {
  trap - INT TERM EXIT
  echo
  echo "==> Shutting down"
  kill -- -"$backend" 2>/dev/null || true
  kill -- -"$frontend" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

echo
echo "==> Backend  http://localhost:${BACKEND_PORT}  (Django API)"
echo "==> Frontend http://localhost:${FRONTEND_PORT}  <- open this"
echo "==> Ctrl+C stops both"
echo

# Poll instead of `wait -n` (absent in macOS's bash 3.2); exit as soon as
# either server dies so a crash doesn't leave a zombie behind.
while kill -0 "$backend" 2>/dev/null && kill -0 "$frontend" 2>/dev/null; do
  sleep 1
done
