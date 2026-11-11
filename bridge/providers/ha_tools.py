"""Home Assistant Tools for OpenAI-compatible LLM providers.

Executes actions against Home Assistant Core REST API using SUPERVISOR_TOKEN
or custom Long-Lived Access Token.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("chassitant.providers.ha_tools")


def get_token() -> Optional[str]:
    """Retrieve SUPERVISOR_TOKEN or custom token."""
    token = os.getenv("SUPERVISOR_TOKEN") or os.getenv("HOMEASSISTANT_TOKEN")
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


def get_ha_context_snippet() -> str:
    """Read HA_CONTEXT.md if present to provide pre-indexed knowledge."""
    candidates = [
        Path("/data/HA_CONTEXT.md"),
        Path("/app/HA_CONTEXT.md"),
        Path(__file__).resolve().parent.parent.parent / "HA_CONTEXT.md",
    ]
    for c in candidates:
        if c.is_file():
            try:
                content = c.read_text(encoding="utf-8").strip()
                if content:
                    # Limit to first 4000 characters to keep context compact
                    return content[:4000]
            except Exception:
                pass
    return ""


# Standard OpenAI Tool definitions for Home Assistant
HA_TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "ha_get_state",
            "description": "Obtient l'état et les attributs d'une entité Home Assistant précise (ex: 'climate.salon', 'cover.volet_chambre', 'sensor.temperature').",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_id": {
                        "type": "string",
                        "description": "L'identifiant exact de l'entité (ex: 'light.salon', 'cover.salon').",
                    }
                },
                "required": ["entity_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ha_call_service",
            "description": "Exécute une action ou un service sur des appareils Home Assistant (ex: allumer une lumière, ouvrir un volet, régler un thermostat).",
            "parameters": {
                "type": "object",
                "properties": {
                    "domain": {
                        "type": "string",
                        "description": "Le domaine du service (ex: 'light', 'cover', 'climate', 'switch').",
                    },
                    "service": {
                        "type": "string",
                        "description": "L'action à exécuter (ex: 'turn_on', 'turn_off', 'open_cover', 'close_cover', 'set_temperature').",
                    },
                    "service_data": {
                        "type": "object",
                        "description": "Paramètres de l'action (ex: {'entity_id': 'light.salon'} ou {'entity_id': 'climate.salon', 'temperature': 21}).",
                    },
                },
                "required": ["domain", "service"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ha_search",
            "description": "Recherche des entités Home Assistant par domaine (cover, light, climate, sensor, switch) ou par mot-clé.",
            "parameters": {
                "type": "object",
                "properties": {
                    "domain": {
                        "type": "string",
                        "description": "Filtrer par domaine (ex: 'cover', 'light', 'climate', 'sensor').",
                    },
                    "query": {
                        "type": "string",
                        "description": "Mot-clé de recherche (ex: 'salon', 'température', 'cuisine').",
                    },
                },
            },
        },
    },
]


def execute_ha_tool(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a Home Assistant tool call against Core REST API."""
    token = get_token()
    base_url = get_base_url()

    if not token:
        return {"error": "Jeton Home Assistant non disponible (SUPERVISOR_TOKEN requis)."}

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    try:
        if tool_name == "ha_get_state":
            entity_id = arguments.get("entity_id", "").strip()
            if not entity_id:
                return {"error": "entity_id requis"}
            url = f"{base_url}/api/states/{entity_id}"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return {
                    "entity_id": data.get("entity_id"),
                    "state": data.get("state"),
                    "attributes": data.get("attributes", {}),
                    "last_changed": data.get("last_changed"),
                }

        elif tool_name == "ha_call_service":
            domain = arguments.get("domain", "").strip()
            service = arguments.get("service", "").strip()
            data = arguments.get("service_data", {})
            if not domain or not service:
                return {"error": "domain et service sont requis"}

            url = f"{base_url}/api/services/{domain}/{service}"
            body = json.dumps(data).encode("utf-8")
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                return {"success": True, "result": res}

        elif tool_name == "ha_search":
            domain_filter = (arguments.get("domain") or "").strip().lower()
            query_filter = (arguments.get("query") or "").strip().lower()

            url = f"{base_url}/api/states"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                states = json.loads(resp.read().decode("utf-8"))

            matched = []
            for st in states:
                eid = st.get("entity_id", "")
                name = st.get("attributes", {}).get("friendly_name", "")
                dom = eid.split(".")[0] if "." in eid else ""

                if domain_filter and dom != domain_filter:
                    continue
                if query_filter:
                    if query_filter not in eid.lower() and query_filter not in name.lower():
                        continue

                matched.append({
                    "entity_id": eid,
                    "name": name,
                    "state": st.get("state"),
                })
                if len(matched) >= 30:
                    break

            return {"count": len(matched), "entities": matched}

        else:
            return {"error": f"Outil inconnu : {tool_name}"}

    except urllib.error.HTTPError as http_err:
        try:
            err_body = http_err.read().decode("utf-8")
        except Exception:
            err_body = str(http_err)
        logger.error("HTTP error executing %s: %s", tool_name, err_body)
        return {"error": f"Erreur Home Assistant ({http_err.code}): {err_body}"}
    except Exception as ex:
        logger.error("Exception executing %s: %s", tool_name, ex)
        return {"error": str(ex)}
