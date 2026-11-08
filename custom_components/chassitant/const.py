"""Constants for the Chassitant integration."""

from typing import Final

DOMAIN: Final = "chassitant"

# Configuration keys
CONF_HOST: Final = "host"
CONF_PORT: Final = "port"
CONF_API_KEY: Final = "api_key"
CONF_MODEL: Final = "model"
CONF_EFFORT: Final = "effort"
CONF_PROMPT: Final = "prompt"
CONF_TIMEOUT: Final = "timeout"
CONF_SKIP_PERMISSIONS: Final = "dangerously_skip_permissions"

# Defaults
DEFAULT_HOST: Final = "c211720a-chassitant-agy"
DEFAULT_PORT: Final = 8099
DEFAULT_TIMEOUT: Final = 60
DEFAULT_MODEL: Final = "default"
DEFAULT_EFFORT: Final = "high"
DEFAULT_SKIP_PERMISSIONS: Final = True
DEFAULT_PROMPT: Final = (
    "Tu es l'assistant vocal intelligent de la maison. "
    "Réponds de manière concise, claire et naturelle en français. "
    "Lorsque tu effectues une action domotique, confirme brièvement ce qui a été fait."
)

EFFORT_OPTIONS: Final = ["low", "medium", "high", "xhigh", "max"]

SERVICE_ASK: Final = "ask"
SERVICE_CLEAR_CONVERSATION: Final = "clear_conversation"
