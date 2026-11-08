#!/usr/bin/env bash
set -e

echo "================================================================"
echo " 🌟 CHASSITANT AGY — CHATBOT IA & BRIDGE HOME ASSISTANT 🌟"
echo "================================================================"

echo "[Chassitant] Initialisation du stockage persistant..."
mkdir -p /data/.gemini/antigravity-cli
mkdir -p /root/.gemini

# Symlink root's gemini directory to persistent /data
ln -sfn /data/.gemini/antigravity-cli /root/.gemini/antigravity-cli
export HOME="/root"
export PATH="/usr/local/bin:/root/.local/bin:/root/bin:$PATH"
export CHASSITANT_DATA_DIR="/data"
export INGRESS_PORT="${INGRESS_PORT:-8098}"
export PORT="${PORT:-8099}"

# Auto-configure ha-mcp if Supervisor is available
if [ -n "$SUPERVISOR_TOKEN" ]; then
    echo "[Chassitant] Détection du Supervisor : Auto-configuration de ha-mcp..."
    python3 -c "import sys; sys.path.insert(0, '/app'); from bridge.mcp_manager import McpManager; McpManager().auto_configure_homeassistant_mcp()" || true
fi

# Optional: Run ttyd on port 8097 for terminal debugging if needed
if [ -x /usr/local/bin/ttyd ]; then
    echo "[Chassitant] Démarrage du terminal CLI auxiliaire (port 8097)..."
    ttyd -W -p 8097 -t fontSize=14 /app/onboarding.sh >/dev/null 2>&1 &
fi

echo "[Chassitant] Démarrage du serveur Chatbot Ingress (port ${INGRESS_PORT}) et Bridge Assist (port ${PORT})..."
exec python3 /app/bridge/server.py
