"""Universal OpenAI-compatible streaming provider for Groq, OpenRouter, and local Ollama."""

from __future__ import annotations

import json
import logging
import time
import urllib.request
import urllib.error
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

from bridge.providers.base import BaseProvider
from bridge.providers.ha_tools import HA_TOOL_DEFINITIONS, execute_ha_tool, get_ha_context_snippet

logger = logging.getLogger("chassitant.providers.openai_compatible")


DEFAULT_MODELS: Dict[str, List[Dict[str, str]]] = {
    "groq": [
        {"id": "llama-3.3-70b-versatile", "name": "Llama 3.3 70B Versatile (Recommandé, Gratuit & Ultra-rapide)"},
        {"id": "llama-3.1-8b-instant", "name": "Llama 3.1 8B Instant (Instantané)"},
        {"id": "mixtral-8x7b-32768", "name": "Mixtral 8x7B (32k context)"},
        {"id": "gemma2-9b-it", "name": "Gemma 2 9B (Google)"},
    ],
    "openrouter": [
        {"id": "deepseek/deepseek-r1:free", "name": "DeepSeek R1 (Raisonnement, 100% Gratuit :free)"},
        {"id": "meta-llama/llama-3.3-70b-instruct:free", "name": "Llama 3.3 70B (Gratuit :free)"},
        {"id": "mistralai/mistral-small-24b-instruct-2501:free", "name": "Mistral Small 24B (Gratuit :free)"},
        {"id": "google/gemini-2.0-flash-exp:free", "name": "Gemini 2.0 Flash Exp (Gratuit :free)"},
        {"id": "anthropic/claude-3.7-sonnet", "name": "Claude 3.7 Sonnet (Anthropic)"},
        {"id": "openai/gpt-4o", "name": "GPT-4o (OpenAI)"},
    ],
    "ollama": [
        {"id": "llama3.2", "name": "Llama 3.2 (3B - Local rapide)"},
        {"id": "qwen2.5", "name": "Qwen 2.5 (Local domotique)"},
        {"id": "mistral", "name": "Mistral 7B (Local)"},
    ],
}


class OpenAICompatibleProvider(BaseProvider):
    """Handles communication with any OpenAI-compatible API endpoint."""

    def __init__(
        self,
        provider_id: str,
        display_name: str,
        description: str,
        base_url: str,
        api_key: Optional[str] = None,
        default_model: Optional[str] = None,
    ) -> None:
        self._provider_id = provider_id
        self._display_name = display_name
        self._description = description
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or ""
        self.default_model = default_model or (DEFAULT_MODELS.get(provider_id, [{}])[0].get("id", "default"))

    @property
    def provider_id(self) -> str:
        return self._provider_id

    @property
    def display_name(self) -> str:
        return self._display_name

    @property
    def description(self) -> str:
        return self._description

    def is_configured(self) -> bool:
        if self._provider_id == "ollama":
            return bool(self.base_url)
        return bool(self.api_key and self.api_key.strip())

    def check_auth(self, timeout: int = 15) -> Tuple[bool, str]:
        if not self.is_configured():
            if self._provider_id == "ollama":
                return False, f"URL Ollama non configurée (ex: http://localhost:11434/v1)."
            return False, f"Clé API non configurée pour {self.display_name}."

        url = f"{self.base_url}/models"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status in (200, 201):
                    return True, f"Connexion réussie à {self.display_name} !"
                return False, f"Statut inattendu ({resp.status})"
        except urllib.error.HTTPError as http_err:
            return False, f"Erreur d'authentification ({http_err.code}): {http_err.reason}"
        except Exception as ex:
            return False, f"Erreur de connexion : {ex}"

    def list_models(self) -> List[Dict[str, str]]:
        # Return curated list for fast UI rendering
        return DEFAULT_MODELS.get(self._provider_id, [
            {"id": "default", "name": f"{self.display_name} (Modèle par défaut)"}
        ])

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
        if not self.is_configured():
            yield {
                "type": "error",
                "error": f"Le fournisseur '{self.display_name}' n'est pas configuré. Veuillez renseigner sa clé API ou son URL dans les Paramètres.",
            }
            return

        chosen_model = model if (model and model != "default") else self.default_model

        yield {"type": "status", "message": f"Connexion à {self.display_name} ({chosen_model})..."}
        yield {"type": "init", "conversation_id": conversation_id or "default"}

        # Build system prompt with pre_prompt and HA_CONTEXT
        system_parts = []
        if pre_prompt and pre_prompt.strip():
            system_parts.append(pre_prompt.strip())

        ctx = get_ha_context_snippet()
        if ctx:
            system_parts.append(
                f"\n--- INVENTAIRE & CAPTEURS HOME ASSISTANT ACTUELS ---\n{ctx}\n"
                f"Utilise directement ces entités pour répondre ou piloter la maison.\n"
            )

        system_parts.append(
            "Tu as accès à des outils pour piloter Home Assistant : ha_get_state, ha_call_service, ha_search. "
            "Utilise-les lorsque l'utilisateur te demande d'effectuer une action ou de vérifier un état."
        )
        system_content = "\n\n".join(system_parts)

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": prompt},
        ]

        accumulated_full_text = ""
        step_counter = 0
        last_usage: Dict[str, Any] = {}
        start_time = time.time()
        max_tool_rounds = 5  # safety limit for tool calls loop

        for round_idx in range(max_tool_rounds):
            if cancel_event and getattr(cancel_event, "is_set", lambda: False)():
                yield {"type": "cancelled", "message": "Génération interrompue par l'utilisateur"}
                return

            req_body: Dict[str, Any] = {
                "model": chosen_model,
                "messages": messages,
                "stream": True,
                "stream_options": {"include_usage": True},
                "tools": HA_TOOL_DEFINITIONS,
                "tool_choice": "auto",
            }

            headers = {
                "Content-Type": "application/json",
                "User-Agent": "Francoise-HomeAssistant/1.7.1",
            }
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            if self._provider_id == "openrouter":
                headers["HTTP-Referer"] = "https://github.com/hyndruide/francoise"
                headers["X-Title"] = "Francoise Home Assistant"

            req = urllib.request.Request(
                f"{self.base_url}/chat/completions",
                data=json.dumps(req_body).encode("utf-8"),
                headers=headers,
                method="POST",
            )

            tool_calls_accumulator: Dict[int, Dict[str, Any]] = {}
            turn_text_delta = ""

            try:
                with urllib.request.urlopen(req, timeout=timeout) as response:
                    for raw_line in response:
                        if cancel_event and getattr(cancel_event, "is_set", lambda: False)():
                            yield {"type": "cancelled", "message": "Génération interrompue"}
                            return

                        line = raw_line.decode("utf-8", errors="replace").strip()
                        if not line or not line.startswith("data:"):
                            continue

                        data_str = line[5:].strip()
                        if data_str == "[DONE]":
                            break

                        try:
                            chunk = json.loads(data_str)
                        except Exception:
                            continue

                        if chunk.get("usage"):
                            last_usage = chunk["usage"]

                        choices = chunk.get("choices", [])
                        if not choices:
                            continue

                        delta = choices[0].get("delta", {})

                        # Stream textual response
                        content = delta.get("content")
                        if content:
                            turn_text_delta += content
                            accumulated_full_text += content
                            yield {"type": "text_delta", "delta": content}

                        # Accumulate tool calls if any
                        tool_calls = delta.get("tool_calls", [])
                        for tc in tool_calls:
                            idx = tc.get("index", 0)
                            if idx not in tool_calls_accumulator:
                                tool_calls_accumulator[idx] = {
                                    "id": tc.get("id", f"call_{int(time.time()*1000)}"),
                                    "name": "",
                                    "arguments": "",
                                }
                            fn = tc.get("function", {})
                            if fn.get("name"):
                                tool_calls_accumulator[idx]["name"] += fn["name"]
                            if fn.get("arguments"):
                                tool_calls_accumulator[idx]["arguments"] += fn["arguments"]

            except urllib.error.HTTPError as http_err:
                err_text = ""
                try:
                    err_text = http_err.read().decode("utf-8")
                except Exception:
                    pass
                logger.error("HTTP error from %s: %s (%s)", self.display_name, http_err.code, err_text)
                yield {
                    "type": "error",
                    "error": f"Erreur {self.display_name} ({http_err.code}) : {err_text or http_err.reason}",
                }
                return
            except Exception as ex:
                logger.error("Streaming error with %s: %s", self.display_name, ex)
                yield {"type": "error", "error": f"Erreur de communication : {ex}"}
                return

            # If no tool calls were requested, we are done!
            if not tool_calls_accumulator:
                break

            # Execute the tool calls against Home Assistant
            assistant_msg: Dict[str, Any] = {
                "role": "assistant",
                "content": turn_text_delta or None,
                "tool_calls": [],
            }

            for idx, tc in sorted(tool_calls_accumulator.items()):
                t_name = tc.get("name", "")
                t_args_str = tc.get("arguments", "{}")
                t_id = tc.get("id", f"call_{idx}")

                try:
                    t_args = json.loads(t_args_str) if t_args_str else {}
                except Exception:
                    t_args = {}

                assistant_msg["tool_calls"].append({
                    "id": t_id,
                    "type": "function",
                    "function": {"name": t_name, "arguments": t_args_str},
                })

                step_counter += 1
                yield {
                    "type": "tool_start",
                    "tool": t_name,
                    "parameters": t_args,
                    "step_index": step_counter,
                }

                t_start = time.time()
                t_result = execute_ha_tool(t_name, t_args)
                t_duration = time.time() - t_start

                yield {
                    "type": "tool_end",
                    "tool": t_name,
                    "duration": t_duration,
                    "output": json.dumps(t_result, ensure_ascii=False),
                    "step_index": step_counter,
                }

                # Add to messages history for the next round
                messages.append(assistant_msg)
                messages.append({
                    "role": "tool",
                    "tool_call_id": t_id,
                    "name": t_name,
                    "content": json.dumps(t_result, ensure_ascii=False),
                })

        duration = time.time() - start_time
        yield {
            "type": "done",
            "response": accumulated_full_text,
            "duration_seconds": duration,
            "usage": last_usage,
        }
