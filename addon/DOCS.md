# Documentation du module Chassitant (Antigravity agy)

Ce module complémentaire permet d'exécuter **Antigravity CLI (`agy`)** directement en local sur votre serveur Home Assistant sous Docker, 24h/24 et 7j/7.

---

## 🚀 Première utilisation & Authentification Google (Méthode 1)

1. Après avoir installé et démarré le module, cliquez sur **Chassitant agy** dans la barre latérale gauche de Home Assistant (ou sur **Ouvrir l'interface utilisateur web**).
2. Le terminal Ingress s'ouvre.
3. `agy` affiche une URL d'authentification Google sécurisée.
4. Ouvrez cette URL dans votre navigateur, connectez-vous avec votre compte Google et acceptez l'autorisation.
5. Copiez le code d'autorisation affiché par Google.
6. Collez-le dans le terminal et appuyez sur **Entrée**.
7. C'est tout ! Vos identifiants sont sauvegardés de façon permanente dans le volume `/data` de Home Assistant.

---

## 🔗 Connexion avec l'intégration Home Assistant Assist

1. Allez dans **Paramètres > Appareils et services > Ajouter une intégration > Chassitant**.
2. Renseignez :
   - **Hôte** : `localhost` (ou l'IP locale de votre Home Assistant)
   - **Port** : `8099`
   - **Jeton API** : Le jeton affiché dans le journal de démarrage de l'Add-on.
3. Allez dans **Paramètres > Assistants vocaux > Assist** et choisissez **Antigravity agy** comme moteur de conversation.
