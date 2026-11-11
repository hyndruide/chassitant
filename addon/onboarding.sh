#!/usr/bin/env bash
clear

echo "================================================================"
echo " 🌟 CHASSITANT — TERMINAL D'AUTHENTIFICATION & SYSTÈME 🌟"
echo "================================================================"
echo ""

export PATH="/usr/local/bin:/root/.local/bin:/root/bin:$PATH"
export HOME="/root"
export CODEX_HOME="/data/.codex"

# Detect active provider from persisted config
ACTIVE_PROVIDER="agy"
if [ -f /data/chassitant_config.json ]; then
    ACTIVE_PROVIDER=$(python3 -c "import json; print(json.load(open('/data/chassitant_config.json')).get('active_provider', 'agy'))" 2>/dev/null || echo "agy")
elif [ -f /app/chassitant_config.json ]; then
    ACTIVE_PROVIDER=$(python3 -c "import json; print(json.load(open('/app/chassitant_config.json')).get('active_provider', 'agy'))" 2>/dev/null || echo "agy")
fi

if [ "$ACTIVE_PROVIDER" = "codex" ]; then
    echo "🟢 Fournisseur actif : OpenAI Codex CLI (Compte ChatGPT)"
    echo "----------------------------------------------------------------"
    STATUS_OUT=$(codex login status 2>&1 || true)
    if echo "$STATUS_OUT" | grep -qi "logged in"; then
        echo "✅ Statut : Session ChatGPT active !"
        echo "   $STATUS_OUT"
        echo ""
        echo "💡 Vous êtes déjà connecté. Pour changer de compte ou vous reconnecter :"
        echo "   codex logout && codex login --device-auth"
    else
        echo "👉 Lancement de la procédure de connexion (Device Auth)..."
        echo "Suivez les instructions pour associer votre compte ChatGPT :"
        echo "----------------------------------------------------------------"
        echo ""
        codex login --device-auth || true
    fi
elif [ "$ACTIVE_PROVIDER" = "agy" ]; then
    echo "🔵 Fournisseur actif : Google Antigravity (agy)"
    echo "----------------------------------------------------------------"
    if [ -d /root/.gemini ] && [ -f /data/.gemini/oauth_creds.json ]; then
        echo "✅ Statut : Session Google Antigravity active !"
        echo "💡 Pour vous reconnecter ou relancer l'outil CLI : tapez 'agy'"
    else
        echo "👉 Lancement d'Antigravity CLI (agy)..."
        echo "Suivez les instructions à l'écran pour vous connecter :"
        echo "----------------------------------------------------------------"
        echo ""
        agy || true
    fi
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
