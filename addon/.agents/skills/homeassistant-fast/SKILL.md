---
name: homeassistant-fast
description: Guide d'exécution ultra-rapide pour Home Assistant. À utiliser systématiquement pour la recherche d'entités (volets, lumières, chauffage, météo), le pilotage d'appareils et la génération de cartes Lovelace sans latence ni saturation de contexte.
---

# Home Assistant Fast Runbook

Ce skill fournit les règles et modèles pour interagir rapidement avec Home Assistant via `ha-mcp` en minimisant la latence et les tokens.

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

## 2. Modèles de Cartes Lovelace Recommandés

### 2.1 Carte Volets (Grid Tile ou Entities)
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

### 2.2 Carte Météo, Chauffage & Températures (Sans interrupteurs)
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

## 3. Règle d'or pour la rapidité
1. **ZÉRO `ha_get_overview()`** : 1 seul appel ciblé par domaine `ha_search` ou `ha_get_state`.
2. **Génération directe en 1 tour** : Fournir immédiatement le YAML complet dans un bloc `yaml`.
