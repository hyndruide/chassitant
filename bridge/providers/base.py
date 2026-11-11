"""Base class for all AI agent and LLM providers in Françoise."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple


class BaseProvider(ABC):
    """Abstract interface defining the contract for AI providers."""

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Unique identifier (e.g. 'agy', 'groq', 'openrouter', 'ollama')."""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name (e.g. 'Google Antigravity (agy)')."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Brief description of the provider and its quota model."""
        ...

    @abstractmethod
    def is_configured(self) -> bool:
        """Check if required binary, URL or API key is set."""
        ...

    @abstractmethod
    def check_auth(self, timeout: int = 15) -> Tuple[bool, str]:
        """Check if authentication or connection is currently valid."""
        ...

    @abstractmethod
    def list_models(self) -> List[Dict[str, str]]:
        """Return available models [{'id': '...', 'name': '...'}]."""
        ...

    @abstractmethod
    def process_stream(
        self,
        prompt: str,
        conversation_id: Optional[str] = None,
        model: Optional[str] = None,
        effort: Optional[str] = None,
        timeout: int = 300,
        pre_prompt: Optional[str] = None,
        on_proc_started: Optional[Callable[[Any], None]] = None,
        cancel_event: Optional[Any] = None,
    ) -> Iterator[Dict[str, Any]]:
        """
        Stream events from the provider.
        Yields:
          - {"type": "status", "message": ...}
          - {"type": "init", "conversation_id": ...}
          - {"type": "tool_start", "tool": ..., "parameters": ..., "step_index": ...}
          - {"type": "tool_end", "tool": ..., "duration": ..., "output": ...}
          - {"type": "text_delta", "delta": ...}
          - {"type": "done", "response": ..., "duration_seconds": ..., "usage": ...}
          - {"type": "cancelled", "message": ...}
          - {"type": "error", "error": ...}
        """
        ...
