"""Authentication and configuration manager for Chassitant Bridge."""

import json
import os
import secrets
from pathlib import Path
from typing import Any, Dict, Optional

CONFIG_FILE_NAME = "chassitant_config.json"


class AuthManager:
    """Manages local API keys and configuration for Chassitant Bridge."""

    def __init__(self, config_dir: Optional[Path] = None) -> None:
        if config_dir is None:
            # Check environment variable for custom data directory (e.g. Docker /data)
            data_env = os.getenv("CHASSITANT_DATA_DIR")
            if data_env and Path(data_env).is_dir():
                config_dir = Path(data_env)
            else:
                config_dir = Path(__file__).resolve().parent.parent

        self.config_dir = config_dir
        self.config_path = self.config_dir / CONFIG_FILE_NAME
        self._config: Dict[str, Any] = {}
        self.load_or_create_config()

    def load_or_create_config(self) -> Dict[str, Any]:
        """Load configuration from file or create a new one with a secure random token."""
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    self._config = json.load(f)
            except Exception as err:
                print(f"[AuthManager] Warning: failed to read {self.config_path} ({err}), recreating...")
                self._config = {}

        # Check environment variable first
        env_token = os.getenv("CHASSITANT_API_KEY")
        if env_token:
            self._config["api_key"] = env_token

        # If no key set, generate a strong random token
        if not self._config.get("api_key"):
            self._config["api_key"] = secrets.token_hex(20)

        # Default options
        self._config.setdefault("port", 8099)
        self._config.setdefault("host", "0.0.0.0")
        self._config.setdefault("timeout", 60)
        self._config.setdefault("dangerously_skip_permissions", True)
        self._config.setdefault("default_model", "default")
        self._config.setdefault("default_effort", "high")

        self.save_config()
        return self._config

    def save_config(self) -> None:
        """Persist current configuration to disk."""
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self._config, f, indent=2, ensure_ascii=False)
        except Exception as err:
            print(f"[AuthManager] Error saving config to {self.config_path}: {err}")

    def get_api_key(self) -> str:
        """Return the active API key."""
        return self._config.get("api_key", "")

    def validate_token(self, token: Optional[str]) -> bool:
        """Verify if a provided Bearer token matches the configured API key."""
        if not token:
            return False
        configured_key = self.get_api_key()
        if not configured_key:
            return True  # If no key is configured (open access mode)
        # Use constant-time comparison to prevent timing attacks
        return secrets.compare_digest(token.strip(), configured_key.strip())

    @property
    def config(self) -> Dict[str, Any]:
        """Return a copy of current configuration."""
        return dict(self._config)
