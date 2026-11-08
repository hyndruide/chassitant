#!/usr/bin/env bash
set -e

echo "[Chassitant] Initialisation du stockage persistant..."
mkdir -p /data/.gemini/antigravity-cli
mkdir -p /root/.gemini

# Symlink root's gemini directory to persistent /data
ln -sfn /data/.gemini/antigravity-cli /root/.gemini/antigravity-cli
export HOME="/root"
export PATH="/usr/local/bin:/root/.local/bin:/root/bin:$PATH"
export CHASSITANT_DATA_DIR="/data"

echo "[Chassitant] Démarrage du serveur Bridge Chassitant (port 8099)..."
python3 /app/bridge/server.py &
BRIDGE_PID=$!

INGRESS_PORT="${INGRESS_PORT:-8098}"
echo "[Chassitant] Démarrage du terminal Ingress sur le port ${INGRESS_PORT}..."
ttyd -W -p "${INGRESS_PORT}" -t fontSize=15 -t theme='{"background": "#1e1e1e"}' /app/onboarding.sh &
TTYD_PID=$!

# Trap signals for graceful shutdown
trap "kill -TERM $BRIDGE_PID $TTYD_PID 2>/dev/null; exit 0" SIGTERM SIGINT

# Keep script running
wait -n $BRIDGE_PID $TTYD_PID
