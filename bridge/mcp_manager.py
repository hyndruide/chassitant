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


FULL_DISABLED_TOOLS = "ha_get_overview,ha_get_automation_traces,ha_get_camera_image"

ECO_DISABLED_TOOLS = (
    "ha_get_overview,ha_get_automation_traces,ha_get_camera_image,"
    "ha_manage_radio,ha_manage_backup,ha_manage_pipeline,ha_get_hacs_info,"
    "ha_manage_hacs,ha_manage_blueprints,ha_report_issue,ha_manage_updates,"
    "ha_manage_theme,ha_get_app,ha_manage_app,ha_remove_area_or_floor,ha_set_area_or_floor,"
    "ha_config_get_calendar_events,ha_config_remove_calendar_event,ha_config_set_calendar_event,"
    "ha_config_get_category,ha_config_remove_category,ha_config_set_category,"
    "ha_config_remove_automation,ha_config_remove_scene,ha_config_remove_script,"
    "ha_manage_energy_prefs,ha_remove_entity,ha_config_list_groups,ha_config_remove_group,"
    "ha_config_set_group,ha_get_history,ha_get_integration,ha_remove_helpers_integrations,"
    "ha_set_integration,ha_config_get_label,ha_config_remove_label,ha_config_set_label,"
    "ha_get_logs,ha_get_device,ha_remove_device,ha_set_device,"
    "ha_config_delete_dashboard_resource,ha_config_list_dashboard_resources,ha_config_set_dashboard_resource,"
    "ha_get_operation_status,ha_restart,ha_get_todo,ha_remove_todo_item,ha_set_todo_item,"
    "ha_get_entity_exposure,ha_get_zone,ha_remove_zone,ha_set_zone,ha_config_list_helpers,ha_config_set_helper"
)


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

    def get_disabled_tools(self, mode: Optional[str] = None) -> str:
        """Return disabled tools list based on mode ('eco' or 'full')."""
        if not mode:
            for p in [Path("/data/chassitant_config.json"), self.home_dir / "chassitant_config.json"]:
                if p.is_file():
                    try:
                        mode = json.loads(p.read_text(encoding="utf-8")).get("mcp_mode", "eco")
                        break
                    except Exception:
                        pass
        clean_mode = (mode or "eco").strip().lower()
        if clean_mode == "full":
            return FULL_DISABLED_TOOLS
        return ECO_DISABLED_TOOLS

    def auto_configure_homeassistant_mcp(
        self,
        custom_token: Optional[str] = None,
        custom_url: Optional[str] = None,
        mode: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Auto-configure homeassistant MCP server inside the container using SUPERVISOR_TOKEN or custom token.
        Supports 'eco' mode (core tools only, saves 15k tokens) or 'full' mode (all tools).
        """
        supervisor_token = (custom_token or "").strip() or get_supervisor_token()
        ha_url = (custom_url or "").strip() or get_homeassistant_url()

        if not supervisor_token:
            return (
                False,
                "SUPERVISOR_TOKEN non détecté automatiquement. Vous pouvez renseigner un jeton d'accès longue durée (LLAT) dans l'interface.",
            )

        disabled_tools = self.get_disabled_tools(mode)

        # Ensure environment has the token & disabled tools
        os.environ["SUPERVISOR_TOKEN"] = supervisor_token
        os.environ["HOMEASSISTANT_TOKEN"] = supervisor_token
        os.environ["HOMEASSISTANT_URL"] = ha_url
        os.environ["ENABLE_MANDATORY_BPS"] = "false"
        os.environ["ENABLE_STRICT_MANDATORY_BPS"] = "false"
        os.environ["DISABLED_TOOLS"] = disabled_tools

        server_entry = {
            "command": "ha-mcp",
            "args": [],
            "env": {
                "HOMEASSISTANT_URL": ha_url,
                "HOMEASSISTANT_TOKEN": supervisor_token,
                "ENABLE_MANDATORY_BPS": "false",
                "ENABLE_STRICT_MANDATORY_BPS": "false",
                "DISABLED_TOOLS": disabled_tools,
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
                logger.info("Saved homeassistant MCP configuration into %s (disabled=%s)", config_path, "eco" if "ha_manage_radio" in disabled_tools else "full")
            except Exception as err:
                logger.warning("Could not write MCP config to %s: %s", config_path, err)

        # 2. Write configuration into Codex CLI config.toml
        self._update_codex_config_toml(ha_url, supervisor_token, disabled_tools)

        # 3. Also register via agy CLI if available
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
                    f"DISABLED_TOOLS={disabled_tools}",
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

        # 4. Also register via codex CLI if available
        codex_binary = shutil.which("codex") or "/usr/local/bin/codex"
        if os.path.isfile(codex_binary):
            try:
                codex_env = os.environ.copy()
                if os.path.isdir("/data/.codex"):
                    codex_env["CODEX_HOME"] = "/data/.codex"
                cmd_codex = [
                    codex_binary,
                    "mcp",
                    "add",
                    "homeassistant",
                    "--command",
                    "ha-mcp",
                    "--env",
                    f"HOMEASSISTANT_URL={ha_url}",
                    "--env",
                    f"HOMEASSISTANT_TOKEN={supervisor_token}",
                    "--env",
                    "ENABLE_MANDATORY_BPS=false",
                    "--env",
                    "ENABLE_STRICT_MANDATORY_BPS=false",
                    "--env",
                    f"DISABLED_TOOLS={disabled_tools}",
                ]
                subprocess.run(cmd_codex, capture_output=True, text=True, timeout=8, check=False, env=codex_env)
            except Exception as codex_err:
                logger.debug("codex mcp add notice: %s", codex_err)

        mode_desc = "Éco (~27 outils essentiels, économise 15k tokens/requête)" if "ha_manage_radio" in disabled_tools else "Complet (80+ outils)"
        msg = f"Serveur MCP Home Assistant configuré avec succès en Mode {mode_desc}."
        return True, msg

    def _update_codex_config_toml(self, ha_url: str, token: str, disabled_tools: str = ECO_DISABLED_TOOLS) -> None:
        """Write homeassistant MCP server configuration into Codex config.toml."""
        codex_dirs = [
            Path("/data/.codex"),
            Path("/root/.codex"),
            self.home_dir / ".codex",
        ]
        seen_files = set()
        for cdir in codex_dirs:
            try:
                cdir.mkdir(parents=True, exist_ok=True)
                cfg_file = cdir / "config.toml"
                resolved = cfg_file.resolve()
                if resolved in seen_files:
                    continue
                seen_files.add(resolved)

                lines: List[str] = []
                if cfg_file.is_file():
                    content = cfg_file.read_text(encoding="utf-8")
                    in_ha_section = False
                    for line in content.splitlines():
                        stripped = line.strip()
                        if stripped.startswith("[mcp_servers.homeassistant"):
                            in_ha_section = True
                            continue
                        elif in_ha_section and stripped.startswith("["):
                            in_ha_section = False
                        if not in_ha_section:
                            lines.append(line)

                text_without_ha = "\n".join(lines).strip()
                if "cli_auth_credentials_store" not in text_without_ha:
                    base_text = 'cli_auth_credentials_store = "file"\n\n' + text_without_ha
                else:
                    base_text = text_without_ha

                ha_section = f"""

[mcp_servers.homeassistant]
command = "ha-mcp"
args = []

[mcp_servers.homeassistant.env]
HOMEASSISTANT_URL = "{ha_url}"
HOMEASSISTANT_TOKEN = "{token}"
ENABLE_MANDATORY_BPS = "false"
ENABLE_STRICT_MANDATORY_BPS = "false"
DISABLED_TOOLS = "{disabled_tools}"
"""
                new_content = (base_text.strip() + ha_section).strip() + "\n"
                cfg_file.write_text(new_content, encoding="utf-8")
                try:
                    os.chmod(cfg_file, 0o600)
                except Exception:
                    pass
                logger.info("Saved homeassistant MCP into Codex config: %s", cfg_file)
            except Exception as err:
                logger.warning("Could not write Codex MCP config to %s: %s", cdir, err)

    def list_mcp_servers(self) -> List[Dict[str, Any]]:
        """List configured MCP servers and their status."""
        servers_map: Dict[str, Dict[str, Any]] = {}
        is_eco = "ha_manage_radio" in self.get_disabled_tools()
        ha_tools_count = 27 if is_eco else 79
        mode_label = "Mode Éco (~27 outils essentiels)" if is_eco else "Mode Complet (79 outils)"

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
                                    "tools_count": ha_tools_count if name == "homeassistant" else 0,
                                    "mode": "eco" if is_eco else "full",
                                    "mode_label": mode_label if name == "homeassistant" else "",
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
                                "tools_count": ha_tools_count if name == "homeassistant" else 0,
                                "mode": "eco" if is_eco else "full",
                                "mode_label": mode_label if name == "homeassistant" else "",
                            }
            except Exception:
                pass

        return list(servers_map.values())
