#!/usr/bin/env bash
clear

echo "================================================================"
echo " 🌟 CHASSITANT AGY — TERMINAL INGRESS HOME ASSISTANT 🌟"
echo "================================================================"
echo ""

export PATH="/usr/local/bin:/root/.local/bin:/root/bin:$PATH"
export HOME="/root"

echo "👉 Lancement d'Antigravity CLI (agy)..."
echo "Suivez les instructions à l'écran pour vous connecter si demandé :"
echo "----------------------------------------------------------------"
echo ""

agy || true

echo ""
echo "----------------------------------------------------------------"
echo "Session terminée. Vous êtes dans le terminal interactif."
echo "Commandes disponibles :"
echo "  - 'agy'                       : connecter votre compte Google (Antigravity)"
echo "  - 'codex login --device-auth' : connecter votre compte ChatGPT (OpenAI)"
echo "----------------------------------------------------------------"

exec /bin/bash
