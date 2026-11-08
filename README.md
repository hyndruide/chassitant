# 🌟 Chassitant — Module Assist Antigravity (`agy`) pour Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/default)
[![GitHub Release](https://img.shields.io/github/v/release/hyndruide/chassitant)](https://github.com/hyndruide/chassitant/releases)

**Chassitant** intègre **Google Antigravity CLI (`agy`)** directement comme moteur de conversation intelligent (**Assist**) dans **Home Assistant**.

Il permet de piloter votre maison, de poser des questions complexes, de consulter l'état de vos entités et d'exécuter des requêtes à la voix ou par écrit grâce à la puissance d'Antigravity.

---

## 🛠️ Deux modes d'installation au choix

### 🟢 Mode 1 : 100 % sur Home Assistant (Module complémentaire Add-on Docker)
> **Recommandé !** Aucun PC requis, tout tourne 24h/24 directement sur votre serveur Home Assistant.

1. **Ajouter la boutique de modules :**
   - Dans Home Assistant, allez dans **Paramètres** > **Modules complémentaires** > **Boutique de modules complémentaires**.
   - Cliquez sur les **3 points** en haut à droite > **Dépôts**.
   - Ajoutez l'URL : `https://github.com/hyndruide/chassitant`
2. **Installer le module :**
   - Recherchez **Chassitant (Antigravity agy)** et cliquez sur **Installer**.
   - Cochez **Afficher dans la barre latérale**, puis cliquez sur **Démarrer**.
3. **Première connexion Google (Méthode 1 - OAuth via Terminal Ingress) :**
   - Cliquez sur **Chassitant agy** dans le menu de gauche de Home Assistant.
   - Le terminal web s'ouvre : ouvrez l'URL Google affichée, connectez-vous avec votre compte, puis collez le code d'autorisation dans la fenêtre.
   - Vos identifiants sont sauvegardés de manière permanente dans Home Assistant !

---

### 💻 Mode 2 : Passerelle PC (Bridge Python)
> Si vous préférez exécuter `agy` directement depuis votre propre PC de bureau.

- Double-cliquez sur `scripts/start_bridge.bat` (Windows) ou lancez `scripts/start_bridge.sh` (Linux/Mac).
- Le script lance la connexion navigateur et affiche votre IP locale et votre jeton secret.

---

## 📥 Installer l'intégration Assist (via HACS)

1. Dans Home Assistant, ouvrez **HACS** > **Intégrations**.
2. Cliquez sur les **3 petits points** en haut à droite > **Dépôts personnalisés** (*Custom repositories*).
3. Ajoutez l'URL suivante :
   - **Dépôt** : `https://github.com/hyndruide/chassitant`
   - **Type** : `Intégration`
4. Cliquez sur **Ajouter**, recherchez **Chassitant** et cliquez sur **Télécharger**.
5. Redémarrez **Home Assistant**.
6. Rendez-vous dans **Paramètres** > **Appareils et services** > **Ajouter une intégration** > **Chassitant**.
   - Si vous utilisez l'Add-on Docker : Hôte `localhost`, Port `8099`.
   - Si vous utilisez le Bridge PC : Hôte `<IP_DE_VOTRE_PC>`, Port `8099`.
7. Dans **Paramètres** > **Assistants vocaux** > **Assist**, sélectionnez **Antigravity agy** comme moteur de conversation.

---

## ⚙️ Options configurables

Depuis **Paramètres > Appareils et services > Chassitant > Configurer** :

| Option | Description | Valeur par défaut |
| :--- | :--- | :--- |
| **Modèle** | Modèle utilisé (`default`, `gemini-3.8-flash-high`, `claude-sonnet-4-6`, etc.) | `default` |
| **Effort de réflexion** | Niveau de raisonnement de l'agent (`low`, `medium`, `high`, `xhigh`, `max`) | `high` |
| **Consignes système** | Prompt système personnalisé transmis à l'assistant | Instructions domotiques concises |
| **Délai d'attente (timeout)** | Temps max alloué avant d'abandonner une requête | `60s` |
| **Auto-approbation MCP** | Autorise `agy` à manipuler les entités sans invite interactive | `Activé` (`--dangerously-skip-permissions`) |

---

## 🤖 Utilisation dans les Automatisations (`chassitant.ask`)

```yaml
action: chassitant.ask
data:
  prompt: "Fais-moi un bilan des lumières allumées et ferme les volets du salon."
response_variable: reponse_ia

action: notify.notify
data:
  message: "{{ reponse_ia.response }}"
```
