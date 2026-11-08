# Documentation du module Chassitant Tout-en-Un (Antigravity agy)

Le module complémentaire **Chassitant** transforme Home Assistant en un hub d'intelligence artificielle conversationnelle autonome propulsé par **Google Antigravity (`agy`)** et le protocole **Model Context Protocol (MCP)**.

---

## 🌟 Fonctionnalités intégrées

1. **Interface Chatbot dans la barre latérale de Home Assistant (Ingress)** :
   - Accessible directement d'un clic dans le menu gauche de Home Assistant.
   - **Tiroir latéral rétractable (Drawer)** avec bouton `☰` pour organiser vos discussions par date (*Aujourd'hui*, *Hier*, *Cette semaine*, *Plus ancien*).
   - Recherche rapide, renommage et suppression de discussions.
   - Rendu Markdown complet avec blocs de code, coloration syntaxique et bouton de copie en 1 clic.
   - Design moderne assorti au thème sombre de Home Assistant, 100% responsive sur mobile et tablette.

2. **Serveur MCP Home Assistant (`ha-mcp`) pré-embarqué** :
   - Inclus nativement dans le conteneur Docker.
   - Connecté automatiquement à votre serveur Home Assistant via le jeton de sécurité Supervisor (`SUPERVISOR_TOKEN`).
   - L'IA a immédiatement accès aux ~80+ outils pour contrôler les appareils, interroger les états, analyser la consommation et créer des cartes Lovelace.

3. **Connexion Google 100% Ingress (Zéro clé API requise)** :
   - Statut en direct dans la barre supérieure et le Drawer.
   - Terminal interactif Google intégré directement dans l'interface Ingress : ouvrez simplement le lien d'autorisation Google affiché, validez avec votre compte Google et collez le code directement dans le terminal.
   - Vos identifiants sont sauvegardés de manière permanente dans `/data/.gemini/antigravity-cli/`.

4. **Compatibilité totale avec Home Assistant Assist** :
   - Serveur Bridge multi-thread actif sur le port interne `8099`.
   - Compatible avec l'intégration HACS `custom_components/chassitant` pour les commandes vocales ou le dialogue Assist.

---

## 🚀 Mise en route rapide

1. Cliquez sur **Chassitant** dans le menu latéral gauche de Home Assistant.
2. Si vous n'êtes pas encore connecté, cliquez sur **Google Auth** dans la barre supérieure :
   - Le terminal interactif Ingress s'affiche.
   - Ouvrez l'URL de connexion Google affichée, autorisez votre compte Google et copiez le code.
   - Collez le code dans le terminal et appuyez sur **Entrée**.
3. Vos discussions sont automatiquement sauvegardées dans `/data/conversations.json` et persistent après redémarrage ou mise à jour.

---

## 🔌 Exemples de demandes à tester avec Chassitant

- *"Donne-moi un aperçu météo et la consommation électrique de la maison"*
- *"Quelles sont les lumières actuellement allumées dans le salon ?"*
- *"Crée une nouvelle carte Lovelace avec les informations de température et d'humidité"*
- *"Vérifie s'il y a des entités indisponibles ou en erreur dans ma domotique"*
