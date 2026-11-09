# 🍸 Françoise — Assistante IA Antigravity (`agy`) 100% autonome pour Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/default)
[![GitHub Release](https://img.shields.io/github/v/release/hyndruide/francoise)](https://github.com/hyndruide/francoise/releases)

**Françoise** permet d'exécuter **Google Antigravity CLI (`agy`)** directement et en toute autonomie sur votre machine **Home Assistant** (sous Docker), 24h/24 et 7j/7, sans nécessiter aucun PC allumé.

Elle s'intègre nativement avec son interface Web (Drawer rétractable, historique des conversations, inventaire des entités `HA_CONTEXT.md`) et comme moteur de conversation intelligent (**Assist**) pour piloter votre maison, répondre à des requêtes complexes et agir directement sur vos entités via le protocole MCP... avec son tempérament légendaire de 40 ans de comptoir au "Rouge et le Noir" !

---

## 🏗️ Architecture 100 % Home Assistant

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                       Machine Home Assistant (24h/24)                       │
│                                                                             │
│  ┌───────────────────────────────┐     ┌─────────────────────────────────┐  │
│  │     Home Assistant Core       │     │   Module complémentaire Add-on  │  │
│  │                               │     │        (Docker autonome)        │  │
│  │  [ Assist : Voix / Chat ]     │     │                                 │  │
│  │              │                │     │   [ Terminal Ingress (Web UI) ] │  │
│  │              ▼                │     │                  │              │  │
│  │  [ Intégration Françoise ]    │HTTP │                  ▼              │  │
│  │  (custom_components)          │────▶│   [ Serveur API (port 8099) ]   │  │
│  │                               │:8099│                  │              │  │
│  │                               │     │                  ▼              │  │
│  │                               │◀────│   [ Antigravity CLI (agy) ]     │  │
│  │  [ Serveur MCP Home Assistant]│ MCP │                  │              │  │
│  │                               │     │   [ Stockage persistant /data ] │  │
│  └───────────────────────────────┘     └─────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 🚀 Installation & Configuration

### Étape 1 : Installer le module complémentaire (Add-on Docker)

1. Dans Home Assistant, allez dans **Paramètres** > **Modules complémentaires (Apps)** > **Boutique**.
2. Cliquez sur les **3 petits points** en haut à droite > **Dépôts**.
3. Ajoutez l'URL : `https://github.com/hyndruide/francoise`
4. Dans la liste des modules, sélectionnez **Françoise (Antigravity agy)** et cliquez sur **Installer**.
5. Activez les options **Démarrer au lancement du système**, **Watchdog**, et **Afficher dans la barre latérale**, puis cliquez sur **Démarrer**.

---

### Étape 2 : Première connexion Google (OAuth via Ingress)

1. Cliquez sur l'onglet **Françoise** dans le menu de gauche de Home Assistant.
2. Cliquez sur la roue crantée ⚙️ en haut à droite > onglet **Terminal**.
3. `agy` affiche l'URL de connexion sécurisée Google :
   ```text
   👉 https://accounts.google.com/o/oauth2/auth?...
   ```
4. Ouvrez ce lien dans votre navigateur, connectez-vous avec votre compte Google et autorisez `agy`.
5. Copiez le code d'autorisation retourné par Google et collez-le dans le terminal Home Assistant.
6. **Terminé !** Vos identifiants sont sauvegardés dans le volume `/data` et persistent après chaque redémarrage.

---

### Étape 3 : Installer l'intégration Assist (Optionnel, via HACS)

1. Dans Home Assistant, ouvrez **HACS** > **Intégrations**.
2. Cliquez sur les **3 petits points** en haut à droite > **Dépôts personnalisés**.
3. Ajoutez :
   - **Dépôt** : `https://github.com/hyndruide/francoise`
   - **Type** : `Intégration`
4. Cliquez sur **Ajouter**, recherchez **Françoise** et cliquez sur **Télécharger**.
5. Redémarrez Home Assistant.
6. Allez dans **Paramètres** > **Appareils et services** > **Ajouter une intégration** > **Françoise** :
   - **Hôte** : `localhost`
   - **Port** : `8099`
   - **Jeton API** : Indiqué dans le journal de démarrage de l'Add-on.

---

### Étape 4 : Activer Françoise comme moteur de conversation Assist

1. Rendez-vous dans **Paramètres** > **Assistants vocaux** > **Assist**.
2. Dans le champ **Moteur de conversation**, sélectionnez **Antigravity agy**.
3. Vous pouvez désormais parler ou écrire à votre assistant IA depuis n'importe où !

---

## ⚙️ Options configurables

Depuis **Paramètres > Modules complémentaires > Françoise > Configuration** ou directement depuis l'interface Web (⚙️ > Modèle & Options) :

| Option | Description | Valeur par défaut |
| :--- | :--- | :--- |
| **Modèle** | Modèle utilisé (`default`, `gemini-2.5-flash`, `gemini-2.5-pro`, `claude-3-7-sonnet`, etc.) | `default` |
| **Effort de réflexion** | Niveau de raisonnement de l'agent (`low`, `medium`, `high`, `xhigh`, `max`) | `low` |
| **Pré-prompt / Consignes** | Rôle et directives de l'assistante | Persona complet de Françoise (70 ans, tenancière du "Rouge et le Noir") |
| **Délai d'attente (timeout)** | Temps max alloué avant d'abandonner une requête | `300s` |
| **Auto-approbation MCP** | Autorise `agy` à manipuler les entités sans invite interactive | `Activé` (`--dangerously-skip-permissions`) |

---

## 🤖 Utilisation dans les Automatisations (`chassitant.ask`)

Vous pouvez également interroger l'assistante depuis vos scripts et automatisations :

```yaml
action: chassitant.ask
data:
  prompt: "Vérifie si toutes les portes sont fermées et fais-moi un résumé court."
response_variable: reponse_ia

action: notify.notify
data:
  message: "{{ reponse_ia.response }}"
```
