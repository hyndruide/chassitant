# 🌟 Chassitant — Module Assist Antigravity (`agy`) pour Home Assistant

**Chassitant** intègre **Google Antigravity CLI (`agy`)** directement comme moteur de conversation intelligent (**Assist**) dans **Home Assistant**.

Il permet de piloter votre maison, de poser des questions complexes, de consulter l'état de vos entités et d'exécuter des requêtes à la voix ou par écrit grâce à la puissance d'Antigravity.

---

## 🏗️ Architecture

```
┌─────────────────────────────────┐                 ┌────────────────────────────────┐
│         Home Assistant          │                 │    Machine hôte avec `agy`     │
│                                 │                 │                                │
│   [ Micro / Voix / Chat Assist ]│                 │   ┌────────────────────────┐   │
│                 │               │   HTTP / JSON   │   │   Chassitant Bridge    │   │
│                 ▼               │   (Bearer Auth) │   │     (port 8099)        │   │
│   [ custom_components/chassitant]────────────────────▶│                        │   │
│                                 │                 │   └───────────┬────────────┘   │
│                                 │                 │               ▼                │
│                                 │                 │   ┌────────────────────────┐   │
│   [ Serveur MCP Home Assistant ]│◀────────────────────│  Antigravity CLI (agy) │   │
│                                 │   Appels Outils │   └────────────────────────┘   │
└─────────────────────────────────┘                 └────────────────────────────────┘
```

- **Sécurité et zéro configuration d'API externe :** Le Bridge s'exécute avec les identifiants locaux d'`agy`. Aucune clé d'API payante n'est nécessaire.
- **Support multi-tours :** Mémorise le contexte de la conversation (`conversation_id`).
- **Autonome :** Grâce au serveur MCP Home Assistant configuré dans `agy`, l'assistant interagit directement avec vos pièces, lumières et capteurs.

---

## 🚀 Démarrage rapide

### 1. Démarrer la passerelle (Bridge) sur votre PC

Le Bridge ne nécessite **aucune installation externe** (utilise la bibliothèque standard Python 3.9+).

- **Sous Windows :**
  Double-cliquez sur `scripts/start_bridge.bat` (ou exécutez `python bridge/server.py`).
- **Sous Linux / macOS :**
  ```bash
  chmod +x scripts/start_bridge.sh
  ./scripts/start_bridge.sh
  ```

#### Première exécution & Authentification (Option 1)
1. Le script vérifie la présence du binaire `agy`.
2. Si vous n'êtes pas encore connecté à Google Antigravity, **une fenêtre de navigateur s'ouvre automatiquement** pour vous connecter avec votre compte Google.
3. Un jeton de sécurité local unique est généré et stocké dans `chassitant_config.json`.
4. La console affiche les informations à renseigner dans Home Assistant :
   ```text
   ====================================================================
   🚀 LE SERVEUR BRIDGE EST EN COURS D'EXÉCUTION !
   ====================================================================
   À renseigner dans Home Assistant :
     • Hôte / IP :  192.168.1.155
     • Port      :  8099
     • Jeton API :  a1b2c3d4e5f6...
   ====================================================================
   ```

---

### 2. Installer le composant dans Home Assistant

1. Copiez le dossier `custom_components/chassitant` dans le répertoire de configuration de Home Assistant :
   ```text
   config/
   └── custom_components/
       └── chassitant/
           ├── __init__.py
           ├── manifest.json
           ├── config_flow.py
           ├── conversation.py
           ├── client.py
           ├── const.py
           ├── services.py
           ├── services.yaml
           └── translations/
   ```
2. Redémarrez **Home Assistant**.
3. Dans Home Assistant, rendez-vous dans **Paramètres** > **Appareils et services** > **Ajouter une intégration**.
4. Recherchez **Chassitant** (ou *Antigravity agy*).
5. Saisissez l'adresse IP de votre PC, le port (`8099`) et le jeton d'authentification affiché par le Bridge.

---

### 3. Activer Chassitant comme Assistant Vocal par défaut

1. Rendez-vous dans **Paramètres** > **Assistants vocaux**.
2. Cliquez sur votre pipeline Assist (ex: *Home Assistant* ou votre assistant Cloud).
3. Dans le champ **Moteur de conversation**, sélectionnez **Antigravity agy**.
4. Testez immédiatement dans l'interface Assist (icône en haut à droite) ou avec vos enceintes/satellites vocaux !

---

## ⚙️ Options configurables

Depuis **Paramètres > Appareils et services > Chassitant > Configurer**, vous pouvez ajuster :

| Option | Description | Valeur par défaut |
| :--- | :--- | :--- |
| **Modèle** | Modèle utilisé (`default`, `gemini-3.8-flash-high`, `claude-sonnet-4-6`, etc.) | `default` |
| **Effort de réflexion** | Niveau de raisonnement de l'agent (`low`, `medium`, `high`, `xhigh`, `max`) | `high` |
| **Consignes système** | Prompt système transmis à l'assistant | Instructions domotiques concises |
| **Délai d'attente (timeout)** | Temps max alloué avant d'abandonner une requête | `60s` |
| **Auto-approbation MCP** | Autorise `agy` à manipuler les entités sans invite interactive | `Activé` (`--dangerously-skip-permissions`) |

---

## 🤖 Utilisation dans les Automatisations (`chassitant.ask`)

Vous pouvez interroger Chassitant depuis vos automatisations et scripts Home Assistant :

```yaml
action: chassitant.ask
data:
  prompt: "Vérifie si des fenêtres sont restées ouvertes et fais-moi un rapport court."
  model: "gemini-3.8-flash-high"
response_variable: resultat_ia

action: notify.persistent_notification
data:
  title: "Rapport Assistant"
  message: "{{ resultat_ia.response }}"
```

---

## 👥 Partager ce module à quelqu'un d'autre

Ce module est conçu pour être 100 % portable :
1. **Aucun identifiant partagé :** Le fichier `.gitignore` protège vos configurations et jetons personnels (`chassitant_config.json`).
2. **Onboarding automatique :** Lorsque votre ami lance `start_bridge.bat`, le Bridge détecte son propre environnement et lui demande de se connecter à **son** propre compte Google.
3. Il copie son jeton local dans son propre Home Assistant.

---

## 🧪 Tests unitaires

Pour exécuter la suite de tests automatisés :
```bash
python -m unittest tests/test_bridge.py
```
