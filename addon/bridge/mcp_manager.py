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
from typing import Any, Dict, List, Optional

logger = logging.getLogger("chassitant.mcp")


class McpManager:
    """Manages MCP server configuration for Antigravity agy."""

    def __init__(self, agy_binary: Optional[str] = None) -> None:
        self.agy_binary = agy_binary or shutil.which("agy") or "/usr/local/bin/agy"
        self.home_dir = Path.home()
        self.mcp_config_path = self.home_dir / ".gemini" / "antigravity-cli" / "mcp_config.json"

    def is_ha_mcp_installed(self) -> bool:
        """Check if ha-mcp binary is installed."""
        return shutil.which("ha-mcp") is not None

    def auto_configure_homeassistant_mcp(self) -> tuple[bool, str]:
        """
        Auto-configure homeassistant MCP server inside the container using SUPERVISOR_TOKEN.
        """
        supervisor_token = os.getenv("SUPERVISOR_TOKEN")
        ha_url = os.getenv("HOMEASSISTANT_URL", "http://supervisor/core")

        if not supervisor_token:
            # Check if running outside Supervisor
            return False, "SUPERVISOR_TOKEN non détecté (hors environnement Home Assistant OS)."

        try:
            self.mcp_config_path.parent.mkdir(parents=True, exist_ok=True)
            config: Dict[str, Any] = {"mcpServers": {}}
            if self.mcp_config_path.exists():
                try:
                    with open(self.mcp_config_path, "r", encoding="utf-8") as f:
                        config = json.load(f)
                except Exception:
                    config = {"mcpServers": {}}

            config.setdefault("mcpServers", {})
            config["mcpServers"]["homeassistant"] = {
                "command": "ha-mcp",
                "args": [],
                "env": {
                    "HOMEASSISTANT_URL": ha_url,
                    "HOMEASSISTANT_TOKEN": supervisor_token,
                },
            }

            with open(self.mcp_config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

            logger.info("Configured homeassistant MCP in %s", self.mcp_config_path)

            # Also execute agy mcp add if agy binary is present
            if self.agy_binary and shutil.which(self.agy_binary):
                try:
                    subprocess.run(
                        [
                            self.agy_binary,
                            "mcp",
                            "add",
                            "--env",
                            f"HOMEASSISTANT_URL={ha_url}",
                            "--env",
                            f"HOMEASSISTANT_TOKEN={supervisor_token}",
                            "homeassistant",
                            "ha-mcp",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=8,
                        check=False,
                    )
                except Exception as cli_err:
                    logger.debug("agy mcp add invocation notice: %s", cli_err)

            return True, "Serveur MCP Home Assistant configuré avec succès en stdio."
        except Exception as err:
            logger.exception("Failed to auto-configure MCP: %s", err)
            return False, f"Erreur lors de la configuration MCP : {err}"

    def list_mcp_servers(self) -> List[Dict[str, Any]]:
        """List configured MCP servers and their status."""
        servers = []
        if self.mcp_config_path.exists():
            try:
                with open(self.mcp_config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for name, details in data.get("mcpServers", {}).items():
                        cmd = details.get("command", "")
                        env = details.get("env", {})
                        servers.append({
                            "name": name,
                            "type": "stdio",
                            "command": cmd,
                            "url": env.get("HOMEASSISTANT_URL", details.get("url", "")),
                            "status": "enabled",
                        })
            except Exception as err:
                logger.warning("Error reading mcp_config.json: %s", err)

        # Fallback to agy mcp list if empty
        if not servers and shutil.which(self.agy_binary):
            try:
                res = subprocess.run(
                    [self.agy_binary, "mcp", "list"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                for line in res.stdout.splitlines()[1:]:
                    parts = line.split()
                    if len(parts) >= 3:
                        servers.append({
                            "name": parts[0],
                            "type": parts[1],
                            "status": parts[2],
                            "url": " ".join(parts[3:]) if len(parts) > 3 else "",
                        })
            except Exception:
                pass

        return servers
