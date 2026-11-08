#!/usr/bin/env bash
set -e

echo "================================================================"
echo " 🌟 CHASSITANT AGY — CHATBOT IA & BRIDGE HOME ASSISTANT 🌟"
echo "================================================================"

# Import S6-overlay container environment if present
if [ -d /var/run/s6/container_environment ]; then
    echo "[Chassitant] Chargement de l'environnement S6-overlay (/var/run/s6)..."
    for var in /var/run/s6/container_environment/*; do
        [ -f "$var" ] && export "$(basename "$var")"="$(cat "$var")"
    done
elif [ -d /run/s6/container_environment ]; then
    echo "[Chassitant] Chargement de l'environnement S6-overlay (/run/s6)..."
    for var in /run/s6/container_environment/*; do
        [ -f "$var" ] && export "$(basename "$var")"="$(cat "$var")"
    done
fi

echo "[Chassitant] Initialisation du stockage persistant (/data)..."
mkdir -p /data/.gemini/config
mkdir -p /data/.gemini/antigravity-cli

# Symlink entire ~/.gemini to /data/.gemini for permanent persistence
if [ ! -L /root/.gemini ]; then
    if [ -d /root/.gemini ]; then
        cp -rn /root/.gemini/* /data/.gemini/ 2>/dev/null || true
        rm -rf /root/.gemini
    fi
    ln -sfn /data/.gemini /root/.gemini
fi

export HOME="/root"
export PATH="/usr/local/bin:/root/.local/bin:/root/bin:$PATH"
export CHASSITANT_DATA_DIR="/data"
export INGRESS_PORT="${INGRESS_PORT:-8098}"
export PORT="${PORT:-8099}"

# Auto-configure ha-mcp
echo "[Chassitant] Auto-configuration du serveur MCP Home Assistant..."
python3 -c "import sys; sys.path.insert(0, '/app'); from bridge.mcp_manager import McpManager; McpManager().auto_configure_homeassistant_mcp()" || true

# Run ttyd on port 8097 with base path /terminal for Ingress Google OAuth & CLI
if [ -x /usr/local/bin/ttyd ]; then
    echo "[Chassitant] Démarrage du terminal Ingress Google (port 8097)..."
    ttyd -W -p 8097 -b /terminal -t fontSize=14 -t theme='{"background": "#121417"}' /app/onboarding.sh &
fi

echo "[Chassitant] Démarrage du serveur Chatbot Ingress (port ${INGRESS_PORT}) et Bridge Assist (port ${PORT})..."
exec python3 /app/bridge/server.py
