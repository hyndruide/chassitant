#!/usr/bin/env bash
clear

echo "================================================================"
echo " 🌟 CHASSITANT AGY — TERMINAL INGRESS HOME ASSISTANT 🌟"
echo "================================================================"
echo ""

# Ensure paths
export PATH="/usr/local/bin:/root/.local/bin:/root/bin:$PATH"

# Check authentication
echo "🔍 Vérification de la session Google..."
if agy -p "ping" --output-format json --print-timeout 5s >/dev/null 2>&1; then
    echo "✅ Authentification Google active et valide !"
    echo "Le Bridge Chassitant tourne en tâche de fond et répond à Assist sur le port 8099."
    echo ""
    echo "Vous pouvez utiliser ce terminal pour interagir avec agy ou inspecter les logs :"
    echo "  - agy --help"
    echo "  - agy mcp list"
    echo "  - agy models"
    echo ""
else
    echo "================================================================"
    echo " ⚠️ PREMIÈRE CONNEXION : AUTHENTIFICATION GOOGLE OAUTH"
    echo "================================================================"
    echo " 1. agy va afficher une URL d'autorisation sécurisée ci-dessous."
    echo " 2. Ouvrez cette URL dans un onglet de votre navigateur."
    echo " 3. Connectez-vous avec votre compte Google habituel."
    echo " 4. Copiez le code d'autorisation fourni par Google."
    echo " 5. Collez-le ici et appuyez sur ENTRÉE."
    echo "================================================================"
    echo ""
    agy
    echo ""
    echo "✅ Connexion terminée ! Vos identifiants sont sauvegardés dans /data."
fi

exec /bin/bash
