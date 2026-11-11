#!/usr/bin/env bash
clear

echo "================================================================"
echo " 🌟 CHASSITANT — TERMINAL D'AUTHENTIFICATION & SYSTÈME 🌟"
echo "================================================================"
echo ""

export PATH="/usr/local/bin:/root/.local/bin:/root/bin:$PATH"
export HOME="/root"
export CODEX_HOME="/root/.codex"

# Detect active provider from persisted config
ACTIVE_PROVIDER="agy"
if [ -f /data/chassitant_config.json ]; then
    ACTIVE_PROVIDER=$(python3 -c "import json; print(json.load(open('/data/chassitant_config.json')).get('active_provider', 'agy'))" 2>/dev/null || echo "agy")
elif [ -f /app/chassitant_config.json ]; then
    ACTIVE_PROVIDER=$(python3 -c "import json; print(json.load(open('/app/chassitant_config.json')).get('active_provider', 'agy'))" 2>/dev/null || echo "agy")
fi

if [ "$ACTIVE_PROVIDER" = "codex" ]; then
    echo "🟢 Fournisseur actif : OpenAI Codex CLI (Compte ChatGPT)"
    echo "👉 Lancement de la procédure de connexion (Device Auth)..."
    echo "Suivez les instructions pour associer votre compte ChatGPT :"
    echo "----------------------------------------------------------------"
    echo ""
    codex login --device-auth || true
elif [ "$ACTIVE_PROVIDER" = "agy" ]; then
    echo "🔵 Fournisseur actif : Google Antigravity (agy)"
    echo "👉 Lancement d'Antigravity CLI (agy)..."
    echo "Suivez les instructions à l'écran pour vous connecter :"
    echo "----------------------------------------------------------------"
    echo ""
    agy || true
else
    echo "⚡ Fournisseur actif : $ACTIVE_PROVIDER"
    echo "Ce moteur IA utilise une clé d'API ou une URL locale (Paramètres)."
    echo "----------------------------------------------------------------"
    echo ""
fi

echo ""
echo "----------------------------------------------------------------"
echo "Session prête. Vous êtes dans le terminal interactif."
echo "Commandes de connexion disponibles à tout moment :"
echo "  - 'codex login --device-auth' : connecter votre compte ChatGPT (OpenAI)"
echo "  - 'agy'                       : connecter votre compte Google (Antigravity)"
echo "----------------------------------------------------------------"

exec /bin/bash
