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

3. **Gestion de l'authentification dans l'interface** :
   - Statut en direct dans la fenêtre de Paramètres (icône ⚙️).
   - Possibilité de renseigner directement une clé API Google Gemini (`AIza...`) pour une utilisation immédiate et permanente sans expiration.
   - Ou connexion Google OAuth interactive.

4. **Compatibilité totale avec Home Assistant Assist** :
   - Serveur Bridge multi-thread actif sur le port interne `8099`.
   - Compatible avec l'intégration HACS `custom_components/chassitant` pour les commandes vocales ou le dialogue Assist.

---

## 🚀 Mise en route rapide (En 2 minutes)

1. Après l'installation ou la mise à jour de l'Add-on, cliquez sur **Chassitant** dans le menu latéral gauche.
2. Si vous n'êtes pas encore connecté, ouvrez **Paramètres (⚙️)** :
   - Entrez votre clé API Google Gemini (disponible gratuitement sur [Google AI Studio](https://aistudio.google.com/app/apikey)) puis cliquez sur **Enregistrer**.
3. Vos discussions sont automatiquement sauvegardées dans `/data/conversations.json` et persistent même après redémarrage ou mise à jour de l'Add-on.

---

## 🔌 Exemples de demandes à tester avec Chassitant

- *"Donne-moi un aperçu météo et la consommation électrique de la maison"*
- *"Quelles sont les lumières actuellement allumées dans le salon ?"*
- *"Crée une nouvelle carte Lovelace avec les informations de température et d'humidité"*
- *"Vérifie s'il y a des entités indisponibles ou en erreur dans ma domotique"*
