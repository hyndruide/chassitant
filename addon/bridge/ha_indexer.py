"""Home Assistant Knowledge & Entity Indexer for Chassitant.

Scans Home Assistant entities via Core REST API, discovers active devices,
categorizes key domains (weather, climate, temperatures, energy/heating, covers, lights),
and generates a concise, pre-indexed context file (HA_CONTEXT.md) for Gemini agy.
This eliminates repetitive ha_search tool calls and cuts card/dashboard creation time to <5s.
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("chassitant.indexer")


def get_token() -> Optional[str]:
    """Retrieve SUPERVISOR_TOKEN or custom token."""
    token = os.getenv("SUPERVISOR_TOKEN")
    if token and token.strip():
        return token.strip()

    s6_paths = [
        Path("/var/run/s6/container_environment/SUPERVISOR_TOKEN"),
        Path("/run/s6/container_environment/SUPERVISOR_TOKEN"),
        Path("/var/run/s6-rc/container_environment/SUPERVISOR_TOKEN"),
        Path("/run/s6-rc/container_environment/SUPERVISOR_TOKEN"),
    ]
    for p in s6_paths:
        if p.is_file():
            try:
                val = p.read_text(encoding="utf-8").strip()
                if val:
                    return val
            except Exception:
                pass
    return None


def get_base_url() -> str:
    """Retrieve Home Assistant Core base URL."""
    url = os.getenv("HOMEASSISTANT_URL")
    if url and url.strip():
        return url.strip().rstrip("/")

    s6_paths = [
        Path("/var/run/s6/container_environment/HOMEASSISTANT_URL"),
        Path("/run/s6/container_environment/HOMEASSISTANT_URL"),
    ]
    for p in s6_paths:
        if p.is_file():
            try:
                val = p.read_text(encoding="utf-8").strip()
                if val:
                    return val.rstrip("/")
            except Exception:
                pass

    return "http://supervisor/core"


class HaIndexer:
    """Indexes Home Assistant entities and maintains AI contextual cheat-sheets."""

    def __init__(self, token: Optional[str] = None, base_url: Optional[str] = None) -> None:
        self.token = token or get_token()
        self.base_url = base_url or get_base_url()

    def fetch_all_states(self) -> List[Dict[str, Any]]:
        """Fetch all entity states from Home Assistant Core REST API."""
        if not self.token:
            logger.warning("No token available for HA states fetch")
            return []

        url = f"{self.base_url}/api/states"
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if isinstance(data, list):
                    return data
        except Exception as err:
            logger.error("Failed to fetch states from %s: %s", url, err)
        return []

    def categorize_entities(self, states: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Categorize entities into key functional groups with smart duplicate filtering."""
        result: Dict[str, Any] = {
            "weather": [],
            "climates": [],
            "temperatures": [],
            "energy_heating": [],
            "covers": [],
            "lights": [],
            "switches": [],
            "binary_sensors": [],
            "total_count": len(states),
            "scanned_at": datetime.now().isoformat(),
        }

        temp_entities = []
        energy_entities = []

        for st in states:
            eid = st.get("entity_id", "")
            domain = eid.split(".")[0] if "." in eid else ""
            attrs = st.get("attributes", {})
            friendly_name = attrs.get("friendly_name", eid)
            state_val = str(st.get("state", ""))
            unit = attrs.get("unit_of_measurement", "")
            device_class = attrs.get("device_class", "")

            item = {
                "entity_id": eid,
                "name": friendly_name,
                "domain": domain,
                "state": state_val,
                "unit": unit,
                "device_class": device_class,
                "is_active": state_val not in ("unavailable", "unknown"),
            }

            if domain == "weather":
                result["weather"].append(item)

            elif domain == "climate":
                result["climates"].append(item)

            elif domain == "cover":
                result["covers"].append(item)

            elif domain == "light":
                # Exclude hidden or unassigned if desired, but keep friendly lights
                result["lights"].append(item)

            elif domain == "switch":
                result["switches"].append(item)

            elif domain == "binary_sensor":
                if device_class in ("motion", "occupancy", "door", "window", "opening", "smoke", "presence"):
                    result["binary_sensors"].append(item)

            elif domain == "sensor":
                # Temperature detection
                if (
                    device_class == "temperature"
                    or unit in ("°C", "°F", "K")
                    or "_temperature" in eid
                    or "température" in friendly_name.lower()
                    or "temperature" in friendly_name.lower()
                ):
                    temp_entities.append(item)

                # Energy & Heating Consumption detection
                name_lower = friendly_name.lower()
                eid_lower = eid.lower()
                is_energy_related = (
                    device_class in ("energy", "power")
                    or unit in ("kwh", "wh", "w", "kw", "kvarh")
                    or any(k in name_lower for k in ("conso", "chauffage", "energie", "énergie", "puissance", "eau chaude", "pompe à chaleur", "linky", "délestage"))
                    or any(k in eid_lower for k in ("conso", "chauffage", "energy", "power", "eau_chaude"))
                )
                if is_energy_related:
                    energy_entities.append(item)

        # Smart sorting: active entities first!
        temp_entities.sort(key=lambda x: (not x["is_active"], x["name"]))
        energy_entities.sort(key=lambda x: (not x["is_active"], x["name"]))
        result["climates"].sort(key=lambda x: (not x["is_active"], x["name"]))
        result["covers"].sort(key=lambda x: (not x["is_active"], x["name"]))
        result["lights"].sort(key=lambda x: (not x["is_active"], x["name"]))
        result["switches"].sort(key=lambda x: (not x["is_active"], x["name"]))

        result["temperatures"] = temp_entities
        result["energy_heating"] = energy_entities

        return result

    def generate_markdown(self, categorized: Dict[str, Any]) -> str:
        """Generate high-density, token-efficient HA_CONTEXT.md for Gemini agy."""
        lines = [
            "# INVENTAIRE HOME ASSISTANT & RACCOURCIS LOVELACE (HA_CONTEXT.md)",
            "",
            "> ⚡ **DIRECTIVE CRITIQUE D'EXÉCUTION RAPIDE :**",
            "> Cet inventaire liste les équipements RÉELLEMENT installés et configurés dans la maison.",
            "> **INTERDICTION FORMELLE d'utiliser `ha_search`** si l'équipement demandé figure dans les tableaux ci-dessous.",
            "> Utilisez DIRECTEMENT les `entity_id` exacts ci-dessous pour répondre ou créer vos cartes Lovelace !",
            "",
            f"*Dernière mise à jour : {categorized.get('scanned_at', 'maintenant')}*",
            "",
        ]

        # 1. Weather
        weather_list = categorized.get("weather", [])
        lines.append("## 1. Météo")
        if weather_list:
            for w in weather_list:
                lines.append(f"- **`{w['entity_id']}`** : {w['name']} (État actuel : {w['state']})")
        else:
            lines.append("- *Aucune entité météo active trouvée.*")
        lines.append("")

        # 2. Climate / Radiators / Thermostats
        climates = categorized.get("climates", [])
        lines.append(f"## 2. Chauffage, Climatisation & Thermostats ({len(climates)} entités)")
        if climates:
            lines.append("| Nom convivial | Entity ID | État |")
            lines.append("| :--- | :--- | :--- |")
            for c in climates:
                badge = "🟢" if c["is_active"] else "⚪ (indispo)"
                lines.append(f"| {c['name']} | `{c['entity_id']}` | {badge} {c['state']} |")
        else:
            lines.append("- *Aucun thermostat trouvé.*")
        lines.append("")

        # 3. Ambient Room Temperatures
        temps = categorized.get("temperatures", [])
        # Filter for top room temperatures (ambient)
        ambient_temps = [t for t in temps if t["is_active"] and not any(k in t["name"].lower() for k in ("minimale", "slope", "chaudiere", "chaudière", "consigne"))]
        lines.append(f"## 3. Températures d'Ambiance Principales ({len(ambient_temps)} actives)")
        if ambient_temps:
            lines.append("| Pièce / Capteur | Entity ID | Valeur |")
            lines.append("| :--- | :--- | :--- |")
            for t in ambient_temps[:20]:
                lines.append(f"| {t['name']} | `{t['entity_id']}` | **{t['state']} {t['unit']}** |")
        lines.append("")

        # 4. Energy & Heating Consumption
        energies = categorized.get("energy_heating", [])
        active_energies = [e for e in energies if e["is_active"]]
        lines.append(f"## 4. Consommation & Énergie Chauffage ({len(active_energies)} capteurs actifs)")
        if active_energies:
            lines.append("| Équipement / Mesure | Entity ID | Valeur Actuelle |")
            lines.append("| :--- | :--- | :--- |")
            for e in active_energies[:20]:
                lines.append(f"| {e['name']} | `{e['entity_id']}` | **{e['state']} {e['unit']}** |")
        lines.append("")

        # 5. Covers / Shutters
        covers = categorized.get("covers", [])
        lines.append(f"## 5. Volets, Stores & Portails ({len(covers)} entités)")
        if covers:
            lines.append("| Nom | Entity ID | Position / État |")
            lines.append("| :--- | :--- | :--- |")
            for cov in covers:
                lines.append(f"| {cov['name']} | `{cov['entity_id']}` | {cov['state']} |")
        lines.append("")

        # 6. Lovelace Fast-Path Card Templates
        lines.extend([
            "---",
            "## 6. RACCOURCIS & MODÈLES DE CARTES LOVELACE PRÊTS À L'EMPLOI",
            "",
            "Pour insérer une nouvelle vue ou carte dans le dashboard Lovelace :",
            "1. `ha_config_get_dashboard(url_path='lovelace')` -> notez `config_hash`.",
            "2. `ha_config_set_dashboard(url_path='lovelace', config_hash=hash, python_transform=...)` avec la carte voulue :",
            "",
            "### Modèle A : Vue Météo & Climat / Chauffage",
            "```yaml",
            "- type: weather-forecast",
            f"  entity: {weather_list[0]['entity_id'] if weather_list else 'weather.home'}",
            "  show_forecast: true",
            "- type: entities",
            "  title: Températures de la Maison",
            "  entities:",
        ])
        for t in ambient_temps[:5]:
            lines.append(f"    - entity: {t['entity_id']}")
            lines.append(f"      name: {t['name']}")
        lines.extend([
            "- type: entities",
            "  title: Consommation Chauffage & Énergie",
            "  entities:",
        ])
        for e in active_energies[:4]:
            lines.append(f"    - entity: {e['entity_id']}")
            lines.append(f"      name: {e['name']}")

        lines.extend([
            "```",
            "",
            "### Modèle B : Vue Volets Roulants",
            "```yaml",
            "- type: horizontal-stack",
            "  title: Commandes Générales Volets",
            "  cards:",
            "    - type: button",
            "      name: Ouvrir Tous",
            "      icon: mdi:arrow-up-bold-box",
            "      tap_action:",
            "        action: call-service",
            "        service: cover.open_cover",
            "        target:",
            f"          entity_id: {[c['entity_id'] for c in covers]}",
            "```",
            "",
        ])

        return "\n".join(lines)

    def run_indexing(
        self,
        work_dir: Optional[str] = None,
        data_dir: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute full indexing and write context and json files."""
        states = self.fetch_all_states()
        categorized = self.categorize_entities(states)
        md_content = self.generate_markdown(categorized)

        # Output targets
        targets_md = []
        targets_json = []

        if work_dir and os.path.isdir(work_dir):
            targets_md.append(Path(work_dir) / "HA_CONTEXT.md")
        if data_dir and os.path.isdir(data_dir):
            targets_md.append(Path(data_dir) / "HA_CONTEXT.md")
            targets_json.append(Path(data_dir) / "ha_inventory.json")

        # Default fallback targets
        default_app = Path("/app")
        default_data = Path("/data")
        default_local = Path(__file__).resolve().parent.parent

        if default_app.is_dir():
            targets_md.append(default_app / "HA_CONTEXT.md")
        if default_data.is_dir():
            targets_md.append(default_data / "HA_CONTEXT.md")
            targets_json.append(default_data / "ha_inventory.json")

        targets_md.append(default_local / "HA_CONTEXT.md")
        targets_json.append(default_local / "ha_inventory.json")

        # Write markdown context files
        written_md = []
        for p in targets_md:
            try:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(md_content, encoding="utf-8")
                written_md.append(str(p))
            except Exception as ex:
                logger.debug("Could not write %s: %s", p, ex)

        # Write JSON inventory
        written_json = []
        for p in targets_json:
            try:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(json.dumps(categorized, indent=2, ensure_ascii=False), encoding="utf-8")
                written_json.append(str(p))
            except Exception as ex:
                logger.debug("Could not write %s: %s", p, ex)

        logger.info(
            "HA Indexing complete: %d entities scanned, %d climates, %d temps, %d energies. Wrote: %s",
            len(states),
            len(categorized.get("climates", [])),
            len(categorized.get("temperatures", [])),
            len(categorized.get("energy_heating", [])),
            written_md,
        )

        return {
            "success": True,
            "total_entities": len(states),
            "counts": {
                "weather": len(categorized.get("weather", [])),
                "climates": len(categorized.get("climates", [])),
                "temperatures": len(categorized.get("temperatures", [])),
                "energy_heating": len(categorized.get("energy_heating", [])),
                "covers": len(categorized.get("covers", [])),
                "lights": len(categorized.get("lights", [])),
                "switches": len(categorized.get("switches", [])),
            },
            "scanned_at": categorized.get("scanned_at"),
            "data": categorized,
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    indexer = HaIndexer()
    res = indexer.run_indexing()
    print(f"Indexing done: {res.get('counts')}")
