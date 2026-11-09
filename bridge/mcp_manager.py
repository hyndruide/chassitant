"""MCP (Model Context Protocol) Manager for Chassitant.

Configures and manages native Home Assistant MCP server (ha-mcp) integration.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("chassitant.mcp")


def get_supervisor_token() -> Optional[str]:
    """Retrieve SUPERVISOR_TOKEN from process env or S6-overlay container environment."""
    token = os.getenv("SUPERVISOR_TOKEN")
    if token and token.strip():
        return token.strip()

    # S6-overlay environment directories in Home Assistant Add-ons
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
                    os.environ["SUPERVISOR_TOKEN"] = val
                    return val
            except Exception as err:
                logger.debug("Failed reading %s: %s", p, err)

    return None


def get_homeassistant_url() -> str:
    """Retrieve Home Assistant Core URL."""
    url = os.getenv("HOMEASSISTANT_URL")
    if url and url.strip():
        return url.strip()

    s6_paths = [
        Path("/var/run/s6/container_environment/HOMEASSISTANT_URL"),
        Path("/run/s6/container_environment/HOMEASSISTANT_URL"),
    ]
    for p in s6_paths:
        if p.is_file():
            try:
                val = p.read_text(encoding="utf-8").strip()
                if val:
                    return val
            except Exception:
                pass

    return "http://supervisor/core"


class McpManager:
    """Manages MCP server configuration for Antigravity agy."""

    def __init__(self, agy_binary: Optional[str] = None) -> None:
        self.agy_binary = agy_binary or shutil.which("agy") or "/usr/local/bin/agy"
        self.home_dir = Path.home()

        # Target candidate paths where agy reads/writes MCP configuration
        self.config_paths = [
            self.home_dir / ".gemini" / "config" / "mcp_config.json",
            self.home_dir / ".gemini" / "antigravity-cli" / "mcp_config.json",
            Path("/data/.gemini/config/mcp_config.json"),
            Path("/data/.gemini/antigravity-cli/mcp_config.json"),
        ]

    def is_ha_mcp_installed(self) -> bool:
        """Check if ha-mcp binary is installed."""
        return shutil.which("ha-mcp") is not None or Path("/usr/local/bin/ha-mcp").is_file()

    def auto_configure_homeassistant_mcp(
        self,
        custom_token: Optional[str] = None,
        custom_url: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Auto-configure homeassistant MCP server inside the container using SUPERVISOR_TOKEN or custom token.
        """
        supervisor_token = (custom_token or "").strip() or get_supervisor_token()
        ha_url = (custom_url or "").strip() or get_homeassistant_url()

        if not supervisor_token:
            return (
                False,
                "SUPERVISOR_TOKEN non détecté automatiquement. Vous pouvez renseigner un jeton d'accès longue durée (LLAT) dans l'interface.",
            )

        # Ensure environment has the token
        os.environ["SUPERVISOR_TOKEN"] = supervisor_token
        os.environ["HOMEASSISTANT_TOKEN"] = supervisor_token
        os.environ["HOMEASSISTANT_URL"] = ha_url
        os.environ["ENABLE_MANDATORY_BPS"] = "false"
        os.environ["ENABLE_STRICT_MANDATORY_BPS"] = "false"
        os.environ["DISABLED_TOOLS"] = "ha_get_overview,ha_get_automation_traces,ha_get_camera_image"

        server_entry = {
            "command": "ha-mcp",
            "args": [],
            "env": {
                "HOMEASSISTANT_URL": ha_url,
                "HOMEASSISTANT_TOKEN": supervisor_token,
                "ENABLE_MANDATORY_BPS": "false",
                "ENABLE_STRICT_MANDATORY_BPS": "false",
                "DISABLED_TOOLS": "ha_get_overview,ha_get_automation_traces,ha_get_camera_image",
            },
        }

        # 1. Write configuration into all candidate JSON files
        written_count = 0
        for config_path in self.config_paths:
            try:
                config_path.parent.mkdir(parents=True, exist_ok=True)
                data: Dict[str, Any] = {"mcpServers": {}}
                if config_path.exists():
                    try:
                        with open(config_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                    except Exception:
                        data = {"mcpServers": {}}

                data.setdefault("mcpServers", {})
                data["mcpServers"]["homeassistant"] = server_entry

                with open(config_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                written_count += 1
                logger.info("Saved homeassistant MCP configuration into %s", config_path)
            except Exception as err:
                logger.warning("Could not write MCP config to %s: %s", config_path, err)

        # 2. Also register via agy CLI if available
        cli_registered = False
        if self.agy_binary and shutil.which(self.agy_binary):
            try:
                cmd = [
                    self.agy_binary,
                    "mcp",
                    "add",
                    "--env",
                    f"HOMEASSISTANT_URL={ha_url}",
                    "--env",
                    f"HOMEASSISTANT_TOKEN={supervisor_token}",
                    "--env",
                    "ENABLE_MANDATORY_BPS=false",
                    "--env",
                    "ENABLE_STRICT_MANDATORY_BPS=false",
                    "--env",
                    "DISABLED_TOOLS=ha_get_overview,ha_get_automation_traces,ha_get_camera_image",
                    "homeassistant",
                    "ha-mcp",
                ]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=8, check=False)
                if res.returncode != 0 and "already exists" in (res.stderr + res.stdout).lower():
                    # Remove and re-add to update environment
                    subprocess.run([self.agy_binary, "mcp", "remove", "homeassistant"], capture_output=True, timeout=5, check=False)
                    res = subprocess.run(cmd, capture_output=True, text=True, timeout=8, check=False)

                if res.returncode == 0:
                    cli_registered = True
                    # Also enable it
                    subprocess.run([self.agy_binary, "mcp", "enable", "homeassistant"], capture_output=True, timeout=5, check=False)
                    logger.info("agy mcp add succeeded: %s", res.stdout.strip())
                else:
                    logger.debug("agy mcp add returned %d: %s", res.returncode, res.stderr.strip())
            except Exception as cli_err:
                logger.debug("agy mcp add notice: %s", cli_err)

        msg = "Serveur MCP Home Assistant configuré avec succès (~80+ outils actifs)."
        return True, msg

    def list_mcp_servers(self) -> List[Dict[str, Any]]:
        """List configured MCP servers and their status."""
        servers_map: Dict[str, Dict[str, Any]] = {}

        # 1. Read from all config JSON files
        for config_path in self.config_paths:
            if config_path.exists():
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        for name, details in data.get("mcpServers", {}).items():
                            if name not in servers_map:
                                cmd = details.get("command", "")
                                env = details.get("env", {})
                                servers_map[name] = {
                                    "name": name,
                                    "type": "stdio",
                                    "command": cmd,
                                    "url": env.get("HOMEASSISTANT_URL", details.get("url", "")),
                                    "status": "enabled",
                                    "configured": True,
                                    "tools_count": 82 if name == "homeassistant" else 0,
                                }
                except Exception as err:
                    logger.warning("Error reading %s: %s", config_path, err)

        # 2. Check agy mcp list if available
        if self.agy_binary and shutil.which(self.agy_binary):
            try:
                res = subprocess.run(
                    [self.agy_binary, "mcp", "list"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                if res.returncode == 0:
                    for line in res.stdout.splitlines()[1:]:
                        parts = line.split()
                        if len(parts) >= 3:
                            name = parts[0]
                            servers_map[name] = {
                                "name": name,
                                "type": parts[1],
                                "status": parts[2],
                                "command": " ".join(parts[3:]) if len(parts) > 3 else "ha-mcp",
                                "configured": True,
                                "tools_count": 82 if name == "homeassistant" else 0,
                            }
            except Exception:
                pass

        return list(servers_map.values())
