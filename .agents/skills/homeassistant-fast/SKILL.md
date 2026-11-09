---
name: homeassistant-fast
description: Guide d'exécution ultra-rapide pour Home Assistant. À utiliser systématiquement pour la recherche d'entités (volets, lumières, chauffage, météo), le pilotage d'appareils et la création réelle de pages et cartes Lovelace dans Home Assistant sans latence ni saturation de contexte.
---

# Home Assistant Fast Runbook

Ce skill fournit les règles et modèles pour interagir rapidement avec Home Assistant via `ha-mcp` en minimisant la latence et les tokens, et en appliquant réellement les créations demandées par l'utilisateur.

## 1. Table de Correspondance Sémantique (Français -> Domaine HA)

| Termes utilisateur | Domaine HA | Outil recommandé |
|---|---|---|
| Volets, stores, persiennes, bannes, velux, garage, portail | `cover` | `ha_search(domain="cover")` ou `ha_get_state(domain="cover")` |
| Lumières, ampoules, éclairage, spots, leds, veilleuse | `light` | `ha_search(domain="light")` ou `ha_get_state(domain="light")` |
| Chauffage, thermostat, clim, radiateurs, pompe à chaleur, consigne | `climate` | `ha_search(domain="climate")` ou `ha_get_state(domain="climate")` |
| Prises, interrupteurs, contacteurs, multiprises, relais | `switch` | `ha_search(domain="switch")` ou `ha_get_state(domain="switch")` |
| Température, humidité, pression | `sensor` | `ha_search(domain="sensor", query="temperature")` |
| Consommation, puissance, électricité, Linky, kWh, Watt, énergie | `sensor` | `ha_search(domain="sensor", query="energy")` |
| Météo, pluie, vent, prévisions | `weather` | `ha_search(domain="weather")` ou `ha_get_state(domain="weather")` |
| Présence, mouvement, ouverture fenêtres / portes | `binary_sensor` | `ha_search(domain="binary_sensor")` |

## 2. Procédure de Création Réelle dans Home Assistant (Dashboards & Vues)

Quand l'utilisateur demande de créer une page, une vue ou d'ajouter une carte dans son tableau de bord :
Ne vous arrêtez PAS à l'affichage du YAML ! Effectuez l'écriture dans Home Assistant :

1. **Obtenir la clé de validation BestPracticeKey :**
   Appelez `ha_get_skill_guide()` et extrayez la clé d'acquittement commençant par `I-HAVE-READ-THE-BEST-PRACTICES-GUIDE-...`.
2. **Obtenir le hash de configuration actuel :**
   Appelez `ha_config_get_dashboard(url_path="lovelace")` (ou du dashboard cible) pour récupérer `config_hash`.
3. **Appliquer l'ajout de la vue via `ha_config_set_dashboard` :**
   ```python
   ha_config_set_dashboard(
       url_path="lovelace",
       config_hash=hash,
       BestPracticeKey=key,
       python_transform="config.setdefault('views', []).append({'title': 'Volets', 'path': 'volets', 'icon': 'mdi:window-shutter', 'cards': [...]})"
   )
   ```
4. **Confirmer à l'utilisateur :**
   Indiquez que la vue a été créée avec succès, donnez son chemin direct (`/lovelace/volets`), et affichez le YAML de la carte créée.

## 3. Modèles de Cartes Lovelace Recommandés

### 3.1 Carte Volets (Grid Tile avec commandes Ouvrir/Fermer)
```yaml
type: grid
title: Volets Roulants
columns: 2
square: false
cards:
  - type: tile
    entity: cover.salon
    features:
      - type: cover-open-close
  - type: tile
    entity: cover.chambre
    features:
      - type: cover-open-close
```

### 3.2 Carte Météo, Chauffage & Températures (Sans interrupteurs)
```yaml
type: vertical-stack
cards:
  - type: weather-forecast
    entity: weather.forecast_home
    show_current: true
    show_forecast: true
  - type: grid
    title: Températures
    columns: 2
    cards:
      - type: tile
        entity: sensor.temperature_salon
        color: deep-orange
      - type: tile
        entity: sensor.temperature_chambre
        color: deep-orange
  - type: grid
    title: Chauffage & Énergie
    columns: 2
    cards:
      - type: tile
        entity: climate.thermostat_salon
      - type: tile
        entity: sensor.consommation_chauffage
        color: purple
```

## 4. Règles Clés de Performance
1. **ZÉRO `ha_get_overview()`** : 1 seul appel ciblé par domaine `ha_search(domain="...")` ou `ha_get_state(domain="...")`.
2. **Exécution complète en 1 tour** : Recherche ➡️ Récupération clé ➡️ Création dashboard ➡️ Confirmation utilisateur.
