#!/usr/bin/env bash
set -euo pipefail

run_headful() {
  export DISPLAY="${DISPLAY:-:99}"
  local width="${XVFB_W:-1920}"
  local height="${XVFB_H:-1080}"
  local depth="${XVFB_D:-24}"
  local vnc_port="${VNC_PORT:-5900}"

  echo "[entrypoint] Starting Xvfb on $DISPLAY (${width}x${height}x${depth})"
  Xvfb "$DISPLAY" -screen 0 "${width}x${height}x${depth}" -ac +extension RANDR +extension GLX &
  XVFB_PID=$!

  echo "[entrypoint] Launching fluxbox window manager"
  fluxbox >/tmp/fluxbox.log 2>&1 &
  FLUXBOX_PID=$!

  echo "[entrypoint] Exposing VNC on port ${vnc_port}"
  x11vnc -display "$DISPLAY" -nopw -listen 0.0.0.0 -forever -shared -rfbport "$vnc_port" >/tmp/x11vnc.log 2>&1 &
  X11VNC_PID=$!

  trap 'kill "$XVFB_PID" "$FLUXBOX_PID" "$X11VNC_PID" 2>/dev/null || true' EXIT
}

if [[ "${TT_HEADLESS:-1}" == "0" ]]; then
  run_headful
else
  echo "[entrypoint] Running in headless mode"
fi

echo "[entrypoint] Running: python main.py $*"
exec python main.py "$@"
