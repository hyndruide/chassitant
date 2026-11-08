#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

echo "Vérification de Python..."
if ! command -v python3 &> /dev/null; then
    if ! command -v python &> /dev/null; then
        echo "[ERREUR] Python 3 n'est pas installé sur ce système."
        exit 1
    else
        PY_CMD="python"
    fi
else
    PY_CMD="python3"
fi

$PY_CMD bridge/server.py
