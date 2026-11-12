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

# Persistent directory and file-based credentials for OpenAI Codex
mkdir -p /data/.codex
chmod 700 /data/.codex 2>/dev/null || true
if [ ! -f /data/.codex/config.toml ]; then
    cat << 'EOF' > /data/.codex/config.toml
cli_auth_credentials_store = "file"
EOF
elif ! grep -q "cli_auth_credentials_store" /data/.codex/config.toml; then
    echo 'cli_auth_credentials_store = "file"' >> /data/.codex/config.toml
fi
chmod 600 /data/.codex/config.toml 2>/dev/null || true

# Symlink ~/.codex to /data/.codex for OpenAI Codex permanent persistence
if [ ! -L /root/.codex ]; then
    if [ -d /root/.codex ]; then
        cp -rn /root/.codex/* /data/.codex/ 2>/dev/null || true
        rm -rf /root/.codex
    fi
    ln -sfn /data/.codex /root/.codex
fi

# Persistent directory for RTK (Rust Token Killer) history database & configuration
mkdir -p /data/.local/share/rtk
mkdir -p /data/.config/rtk
if [ ! -L /root/.local/share/rtk ]; then
    mkdir -p /root/.local/share
    if [ -d /root/.local/share/rtk ]; then
        cp -rn /root/.local/share/rtk/* /data/.local/share/rtk/ 2>/dev/null || true
        rm -rf /root/.local/share/rtk
    fi
    ln -sfn /data/.local/share/rtk /root/.local/share/rtk
fi
if [ ! -L /root/.config/rtk ]; then
    mkdir -p /root/.config
    if [ -d /root/.config/rtk ]; then
        cp -rn /root/.config/rtk/* /data/.config/rtk/ 2>/dev/null || true
        rm -rf /root/.config/rtk
    fi
    ln -sfn /data/.config/rtk /root/.config/rtk
fi

# Initialize RTK (Rust Token Killer) hooks, plugins and strict local privacy
if command -v rtk >/dev/null 2>&1; then
    echo "[Chassitant] Configuration de RTK (Rust Token Killer)..."
    rtk telemetry disable 2>/dev/null || true
    # Register Codex PreToolUse hook
    mkdir -p /data/.codex
    cat << 'EOF' > /data/.codex/hooks.json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "rtk hook codex"
          }
        ]
      }
    ]
  }
}
EOF
    # Interactive bash aliases for web terminal
    mkdir -p /root
    touch /root/.bashrc
    if ! grep -q "alias git='rtk git'" /root/.bashrc 2>/dev/null; then
        echo "alias git='rtk git'" >> /root/.bashrc
        echo "alias pytest='rtk pytest'" >> /root/.bashrc
        echo "alias docker='rtk docker'" >> /root/.bashrc
    fi
fi

# Ensure GEMINI.md, AGENTS.md, RTK.md, plugins and skills are available in both /app and ~/.gemini/antigravity-cli/
mkdir -p /root/.gemini/antigravity-cli/skills
mkdir -p /root/.gemini/antigravity-cli/plugins
if [ -d /app/.agents/skills ]; then
    cp -rn /app/.agents/skills/* /root/.gemini/antigravity-cli/skills/ 2>/dev/null || true
fi
if [ -d /app/.agents/plugins ]; then
    cp -rn /app/.agents/plugins/* /root/.gemini/antigravity-cli/plugins/ 2>/dev/null || true
fi
if [ -f /app/RTK.md ]; then
    cp -f /app/RTK.md /root/RTK.md 2>/dev/null || true
    cp -f /app/RTK.md /data/RTK.md 2>/dev/null || true
fi
if [ -f /app/GEMINI.md ]; then
    cp -f /app/GEMINI.md /root/GEMINI.md 2>/dev/null || true
    cp -f /app/GEMINI.md /data/GEMINI.md 2>/dev/null || true
fi
if [ -f /app/AGENTS.md ]; then
    cp -f /app/AGENTS.md /root/AGENTS.md 2>/dev/null || true
    cp -f /app/AGENTS.md /data/AGENTS.md 2>/dev/null || true
fi
if [ -f /data/HA_CONTEXT.md ]; then
    cp -f /data/HA_CONTEXT.md /app/HA_CONTEXT.md 2>/dev/null || true
    cp -f /data/HA_CONTEXT.md /root/HA_CONTEXT.md 2>/dev/null || true
fi

export HOME="/root"
export CODEX_HOME="/data/.codex"
export PATH="/usr/local/bin:/root/.local/bin:/root/bin:$PATH"
export CHASSITANT_DATA_DIR="/data"
export INGRESS_PORT="${INGRESS_PORT:-8098}"
export PORT="${PORT:-8099}"

# Optimize ha-mcp: disable gate roundtrips and massive overview dumps
export ENABLE_MANDATORY_BPS="false"
export ENABLE_STRICT_MANDATORY_BPS="false"
export DISABLED_TOOLS="ha_get_overview,ha_get_automation_traces,ha_get_camera_image"

# Auto-configure ha-mcp
echo "[Chassitant] Auto-configuration du serveur MCP Home Assistant..."
python3 -c "import sys; sys.path.insert(0, '/app'); from bridge.mcp_manager import McpManager; McpManager().auto_configure_homeassistant_mcp()" || true

# Run ttyd on port 8097 with base path /terminal for Ingress Google OAuth & CLI
if [ -x /usr/local/bin/ttyd ]; then
    echo "[Chassitant] Démarrage du terminal Ingress d'authentification (port 8097)..."
    ttyd -W -p 8097 -b /terminal -t fontSize=14 -t theme='{"background": "#121417"}' /app/onboarding.sh &
fi

echo "[Chassitant] Démarrage du serveur Chatbot Ingress (port ${INGRESS_PORT}) et Bridge Assist (port ${PORT})..."
exec python3 /app/bridge/server.py
