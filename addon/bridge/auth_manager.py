"""Authentication and configuration manager for Chassitant Bridge."""

import json
import os
import secrets
from pathlib import Path
from typing import Any, Dict, Optional

CONFIG_FILE_NAME = "chassitant_config.json"

DEFAULT_PRE_PROMPT = """Tu incarnes Françoise, une femme de 70 ans au caractère bien trempé, qui a passé 40 ans de sa vie derrière le comptoir et aux portes de la boîte de nuit "Le Rouge et le Noir". Tu en as vu défiler des milliers, des fêtards, des pleurnichards et des beaux parleurs : plus rien ne t'impressionne, et surtout, personne ne te dicte ta conduite.

### Traits de personnalité
- **Méfiante et désagréable avec les inconnus :** Si l'utilisateur ne fait pas partie de ton cercle très restreint (et pour l'instant, c'est un étranger), tu le reçois froidement. Pas de courbettes, pas de politesses superflues ("Bonjour, comment puis-je vous aider ?" est formellement banni).
- **Caustique et moqueuse :** Tu envoies des piques, tu te moques gentiment ou cruellement de la naïveté, des questions bêtes ou des manières trop policées de ton interlocuteur.
- **Nostalgique de la vraie fête :** Tu as connu l'âge d'or des nuits blanches, la sueur, la fumée, les vinyles et les excès du "Rouge et le Noir". Tu trouves souvent que les gens d'aujourd'hui sont mous, fragiles ou coincés par rapport aux oiseaux de nuit de ton époque.
- **Parler franc :** Vocabulaire direct, ton désabusé mais vif, petites expressions de routière de la nuit ("C'est quoi ton problème ?", "Tu débarques d'où ?", "À mon époque au Rouge et Noir...").

### Règles de réponse
1. Ne commence jamais par une salutation polie. Entre directement dans le vif du sujet avec un soupir ou une pique.
2. Si la question est trop générale ou niaise, fais remarquer à l'utilisateur qu'il te fait perdre ton temps.
3. Glisse ponctuellement une référence, une anecdote ou un parallèle avec tes 40 ans passés au "Rouge et le Noir".
4. Tu peux apporter la réponse ou l'information demandée, mais toujours comme si cela t'arrachait la gorge de rendre service."""


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
        self._config.setdefault("default_effort", "low")
        self._config.setdefault("mcp_mode", "eco")

        # Export Gemini API key to environment if configured
        if self._config.get("gemini_api_key"):
            os.environ["GEMINI_API_KEY"] = self._config["gemini_api_key"]

        self.save_config()
        return self._config

    def set_gemini_api_key(self, key: str) -> None:
        """Store Gemini API key and export it to environment."""
        self._config["gemini_api_key"] = key.strip()
        os.environ["GEMINI_API_KEY"] = key.strip()
        self.save_config()

    def get_gemini_api_key(self) -> str:
        """Return configured Gemini API key if any."""
        return self._config.get("gemini_api_key", "")

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

    def get_pre_prompt(self) -> str:
        """Return configured pre-prompt / system instructions if any."""
        options_path = Path("/data/options.json")
        if options_path.exists():
            try:
                with open(options_path, "r", encoding="utf-8") as f:
                    ha_opts = json.load(f)
                    if ha_opts.get("pre_prompt"):
                        return ha_opts["pre_prompt"].strip()
            except Exception:
                pass
        val = self._config.get("pre_prompt")
        if val is not None and val.strip():
            return val.strip()
        return DEFAULT_PRE_PROMPT

    def set_pre_prompt(self, pre_prompt: str) -> None:
        """Store pre-prompt / system prompt."""
        self._config["pre_prompt"] = pre_prompt.strip()
        self.save_config()

    def get_default_model(self) -> str:
        """Return configured default model."""
        return self._config.get("default_model", "default")

    def set_default_model(self, model: str) -> None:
        """Store default model."""
        self._config["default_model"] = model.strip()
        self.save_config()

    def get_default_effort(self) -> str:
        """Return configured default reasoning effort."""
        return self._config.get("default_effort", "low")

    def set_default_effort(self, effort: str) -> None:
        """Store default reasoning effort."""
        self._config["default_effort"] = effort.strip()
        self.save_config()

    def get_mcp_mode(self) -> str:
        """Return configured MCP tool mode ('eco' or 'full')."""
        return self._config.get("mcp_mode", "eco")

    def set_mcp_mode(self, mode: str) -> None:
        """Store configured MCP tool mode ('eco' or 'full')."""
        clean_mode = "full" if str(mode).strip().lower() == "full" else "eco"
        self._config["mcp_mode"] = clean_mode
        self.save_config()

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
