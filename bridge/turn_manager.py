"""Background turn manager for Chassitant conversations.

Ensures LLM / agy turns run independently in background threads so that
client disconnections (e.g. navigating to another Home Assistant tab or closing iframe)
never abort the turn or lose generated responses.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("chassitant.turn_manager")

# Context window reference table (in tokens)
MODEL_CONTEXT_LIMITS: Dict[str, int] = {
    # Gemini (1M or 2M)
    "gemini-2.5-flash": 1_048_576,
    "gemini-2.0-flash": 1_048_576,
    "gemini-1.5-flash": 1_048_576,
    "gemini-3.8-flash": 1_048_576,
    "gemini-2.5-pro": 2_097_152,
    "gemini-1.5-pro": 2_097_152,
    # Claude (200k)
    "claude-3-5-sonnet": 200_000,
    "claude-3-7-sonnet": 200_000,
    "claude-3-5-haiku": 200_000,
    "claude-sonnet-4-6": 200_000,
    "claude-opus-4-6": 200_000,
    # OpenAI & Codex
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
    "o3-mini": 200_000,
    "o1": 200_000,
    "o1-mini": 128_000,
    # Open source & Groq / Mistral
    "llama-3.3-70b": 128_000,
    "llama-3.1-70b": 128_000,
    "llama-3.1-8b": 128_000,
    "mistral-large": 128_000,
    "codestral": 256_000,
    "gpt-oss-120b": 128_000,
}


def get_model_context_limit(provider_id: str, model: Optional[str] = None) -> int:
    """Return max context window tokens for given provider and model."""
    m_clean = (model or "").lower().strip()
    p_clean = (provider_id or "").lower().strip()

    for k, limit in MODEL_CONTEXT_LIMITS.items():
        if k in m_clean:
            return limit

    if p_clean == "agy" or "gemini" in m_clean:
        return 1_048_576
    elif "claude" in m_clean or p_clean == "anthropic":
        return 200_000
    elif p_clean == "codex" or "o3" in m_clean or "o1" in m_clean:
        return 200_000 if ("o3" in m_clean or "o1" in m_clean) else 128_000
    return 128_000


def normalize_token_usage(
    raw_usage: Optional[Dict[str, Any]],
    provider_id: str,
    model: Optional[str],
    prompt_text: str = "",
    response_text: str = "",
) -> Dict[str, Any]:
    """Standardize token usage across all LLM providers and compute remaining capacity."""
    context_limit = get_model_context_limit(provider_id, model)
    effective_model = model or "default"

    raw = raw_usage or {}
    has_exact = bool(raw.get("total_tokens") or raw.get("input_tokens") or raw.get("prompt_tokens"))

    if has_exact:
        input_tokens = int(raw.get("input_tokens") or raw.get("prompt_tokens") or 0)
        output_tokens = int(raw.get("output_tokens") or raw.get("completion_tokens") or 0)
        thinking_tokens = int(raw.get("thinking_tokens") or raw.get("reasoning_tokens") or 0)
        total_tokens = int(raw.get("total_tokens") or (input_tokens + output_tokens))
        source = "exact"
    else:
        # Standard token heuristic: ~3.8 chars per token in French / code
        chars_in = len(prompt_text) + 2000
        chars_out = len(response_text)
        input_tokens = max(1, int(chars_in / 3.8))
        output_tokens = max(1, int(chars_out / 3.8))
        thinking_tokens = 0
        total_tokens = input_tokens + output_tokens
        source = "estimated"

    remaining_tokens = max(0, context_limit - total_tokens)
    remaining_pct = round((remaining_tokens / max(1, context_limit)) * 100, 1)
    used_pct = round((total_tokens / max(1, context_limit)) * 100, 1)

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "thinking_tokens": thinking_tokens,
        "total_tokens": total_tokens,
        "context_limit": context_limit,
        "remaining_tokens": remaining_tokens,
        "remaining_percent": remaining_pct,
        "used_percent": used_pct,
        "model": effective_model,
        "source": source,
    }


def build_usage_report(
    conv_store: Any,
    conv_id: str,
    provider: Any,
    model: Optional[str] = None,
) -> Tuple[str, Dict[str, Any]]:
    """Generate a comprehensive usage and quota report without consuming LLM tokens."""
    active_provider_id = getattr(provider, "provider_id", "agy")
    provider_name = getattr(provider, "display_name", active_provider_id)
    model_name = model or "default"
    limit = get_model_context_limit(active_provider_id, model_name)

    conv = conv_store.get_conversation(conv_id) if conv_store else None
    messages = conv.get("messages", []) if conv else []

    # Calculate statistics from conversation
    msg_count = len(messages)
    last_assistant_usage = None
    total_conv_tokens = 0

    for m in messages:
        if m.get("role") == "assistant":
            u = m.get("usage")
            tok = (u.get("total_tokens") if u else None) or m.get("tokens") or 0
            total_conv_tokens += tok
            if u:
                last_assistant_usage = u

    if last_assistant_usage:
        remaining_percent = last_assistant_usage.get("remaining_percent", 100.0)
        remaining_tokens = last_assistant_usage.get("remaining_tokens", limit)
        input_tokens = last_assistant_usage.get("input_tokens", 0)
        output_tokens = last_assistant_usage.get("output_tokens", 0)
        thinking_tokens = last_assistant_usage.get("thinking_tokens", 0)
        total_last = last_assistant_usage.get("total_tokens", input_tokens + output_tokens + thinking_tokens)
        source_label = "Exact (retourné par l'IA)" if last_assistant_usage.get("source") == "exact" else "Estimation locale"
    else:
        remaining_percent = 100.0
        remaining_tokens = limit
        input_tokens = 0
        output_tokens = 0
        thinking_tokens = 0
        total_last = 0
        source_label = "Nouvelle conversation"

    # Fetch provider quota status
    quota_info = {}
    if hasattr(provider, "get_quota_status"):
        try:
            quota_info = provider.get_quota_status() or {}
        except Exception as e:
            logger.warning("Failed to get quota status for report: %s", e)

    plan = quota_info.get("plan") or "Standard"
    account = quota_info.get("account") or "Connecté"
    summary = quota_info.get("summary") or ""

    # Specific quota section depending on provider
    quota_lines = []
    if active_provider_id == "codex":
        h5 = f"{quota_info.get('quota_5h_percent')}% libre" if quota_info.get("quota_5h_percent") is not None else "Actif"
        sem = f"{quota_info.get('quota_week_percent')}% libre" if quota_info.get("quota_week_percent") is not None else "Actif"
        quota_lines.append(f"- **⏳ Quota 5 heures (Burst)** : `{h5}`")
        quota_lines.append(f"- **📅 Quota Semaine (7 jours)** : `{sem}`")
        quota_lines.append(f"- **🔗 Suivi en direct OpenAI** : [chatgpt.com/codex/settings/usage](https://chatgpt.com/codex/settings/usage)")
    elif active_provider_id == "agy":
        quota_lines.append(f"- **🟣 Régime de quota** : **Fair-use continu (0 € / token)**")
        quota_lines.append(f"- **Cadence autorisée** : ~15 requêtes / minute")
        quota_lines.append(f"- **Accès aux modèles** : Gemini 2.5 Flash, Gemini 2.5 Pro, Claude Sonnet")
        quota_lines.append(f"- **ℹ️ Précision** : Google n'applique aucun décompte horaire 5h ou hebdomadaire ; votre accès est permanent.")
    elif active_provider_id == "openrouter":
        credits = quota_info.get("credits_remaining", 0)
        quota_lines.append(f"- **🌐 Solde crédits restants** : `${credits}`")
    elif active_provider_id == "groq":
        quota_lines.append(f"- **⚡ Régime** : **100% Gratuit** (30 requêtes / minute permanentes)")
    elif active_provider_id == "ollama":
        quota_lines.append(f"- **🦙 Régime** : **Local (0 € / 0 limite)** exécuté sur votre machine")
    else:
        if summary:
            quota_lines.append(f"- **Statut** : {summary}")

    quota_section = "\n".join(quota_lines)
    thinking_detail = f"\n  - **Réflexion (Thinking)** : `{thinking_tokens:,}` tokens" if thinking_tokens > 0 else ""

    report_markdown = f"""### 📊 Rapport de Consommation & Quotas (`/usage`)

#### 🧠 Mémoire de Contexte (Discussion active)
- **Modèle sélectionné** : `{model_name}` ({provider_name})
- **Espace disponible** : **{remaining_percent}% libre** (`{remaining_tokens:,}` tokens restants sur `{limit:,}`)
- **Dernier échange** :
  - **Prompt / Entrée** : `{input_tokens:,}` tokens{thinking_detail}
  - **Réponse générée** : `{output_tokens:,}` tokens
  - **Total du message** : `{total_last:,}` tokens *({source_label})*

#### 🔋 Forfait & Quota du Compte
- **Fournisseur actif** : **{provider_name}** (`{active_provider_id}`)
- **Formule / Plan** : `{plan}`
- **Compte associé** : `{account}`
{quota_section}

#### 💬 Statistiques de la Discussion
- **Messages échangés** : `{msg_count}` message(s)
- **Cumul tokens consommés** : `{total_conv_tokens:,}` tokens
- **Coût de la commande `/usage`** : **0 token** (calcul local instantané ⚡)
"""

    report_usage = {
        "total_tokens": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "thinking_tokens": 0,
        "context_limit": limit,
        "remaining_tokens": remaining_tokens,
        "remaining_percent": remaining_percent,
        "source": "exact",
    }

    return report_markdown.strip(), report_usage


class ActiveTurn:
    """Represents a turn running in the background for a conversation."""

    def __init__(self, conv_id: str, prompt: str) -> None:
        self.conv_id = conv_id
        self.prompt = prompt
        self.started_at = time.time()
        self.status = "running"  # "running", "completed", "error", "cancelled"
        self.steps: List[Dict[str, Any]] = []
        self.accumulated_text = ""
        self.result: Optional[Dict[str, Any]] = None
        self.error: Optional[str] = None
        self.proc: Optional[Any] = None
        self._cancelled = threading.Event()
        self._subscribers: List[queue.Queue] = []
        self._lock = threading.Lock()

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled.is_set()

    def set_process(self, proc: Any) -> None:
        """Register the underlying subprocess running this turn."""
        with self._lock:
            self.proc = proc

    def cancel(self) -> bool:
        """Cancel this turn, terminate process and notify all subscribers."""
        with self._lock:
            if self.status != "running":
                return False
            self.status = "cancelled"
            self._cancelled.set()
            proc = self.proc

        if proc:
            try:
                logger.info("Terminating process (pid=%s) for cancelled turn %s", getattr(proc, "pid", "?"), self.conv_id)
                proc.terminate()
                threading.Thread(target=self._kill_proc_if_alive, args=(proc,), daemon=True).start()
            except Exception as ex:
                logger.warning("Error terminating process: %s", ex)

        self.broadcast({
            "type": "cancelled",
            "message": "Génération interrompue par l'utilisateur",
            "accumulated_text": self.accumulated_text,
        })
        return True

    def _kill_proc_if_alive(self, proc: Any) -> None:
        """Wait briefly for process to exit gracefully, then kill if still alive."""
        try:
            time.sleep(1.0)
            if hasattr(proc, "poll") and proc.poll() is None:
                logger.info("Process %s still alive after terminate; killing forcibly", getattr(proc, "pid", "?"))
                proc.kill()
        except Exception:
            pass

    def subscribe(self) -> queue.Queue:
        """Subscribe to live events from this turn."""
        q: queue.Queue = queue.Queue(maxsize=200)
        with self._lock:
            self._subscribers.append(q)
            # Replay current steps if any
            for step in self.steps:
                try:
                    q.put_nowait({
                        "type": "tool_start" if step.get("state") == "running" else "tool_end",
                        "tool": step.get("tool"),
                        "parameters": step.get("parameters"),
                        "duration": step.get("duration", 0),
                    })
                except queue.Full:
                    pass
            if self.accumulated_text:
                try:
                    q.put_nowait({"type": "text_delta", "delta": self.accumulated_text})
                except queue.Full:
                    pass
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        """Remove a subscriber."""
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def broadcast(self, event: Dict[str, Any]) -> None:
        """Broadcast an event to all active subscribers."""
        with self._lock:
            for q in list(self._subscribers):
                try:
                    q.put_nowait(event)
                except queue.Full:
                    pass

    def get_snapshot(self) -> Dict[str, Any]:
        """Return public snapshot of current turn state."""
        return {
            "conv_id": self.conv_id,
            "status": self.status,
            "started_at": self.started_at,
            "elapsed_seconds": round(time.time() - self.started_at, 1),
            "steps": list(self.steps),
            "accumulated_text": self.accumulated_text,
            "is_running": self.status == "running",
        }


class TurnManager:
    """Coordinates active conversation turns."""

    def __init__(self) -> None:
        self._turns: Dict[str, ActiveTurn] = {}
        self._lock = threading.Lock()

    def get_turn(self, conv_id: str) -> Optional[ActiveTurn]:
        """Retrieve active turn for conversation if running."""
        with self._lock:
            turn = self._turns.get(conv_id)
            if turn and turn.status == "running":
                return turn
            return None

    def cancel_turn(self, conv_id: str) -> bool:
        """Cancel active turn for conversation if currently running."""
        with self._lock:
            turn = self._turns.get(conv_id)
            if turn and turn.status == "running":
                return turn.cancel()
            return False

    def start_turn(
        self,
        conv_id: str,
        prompt: str,
        agy_client: Any,
        conv_store: Any,
        model: Optional[str] = None,
        effort: Optional[str] = None,
        timeout: int = 300,
        pre_prompt: Optional[str] = None,
        provider: Optional[Any] = None,
    ) -> ActiveTurn:
        """Start a new background turn for a conversation."""
        with self._lock:
            existing = self._turns.get(conv_id)
            if existing and existing.status == "running":
                return existing

            turn = ActiveTurn(conv_id, prompt)
            self._turns[conv_id] = turn

        active_prov = provider or agy_client
        thread = threading.Thread(
            target=self._run_worker,
            args=(turn, active_prov, conv_store, conv_id, prompt, model, effort, timeout, pre_prompt),
            daemon=True,
            name=f"TurnWorker-{conv_id[:8]}",
        )
        thread.start()
        return turn

    def _run_worker(
        self,
        turn: ActiveTurn,
        provider: Any,
        conv_store: Any,
        conv_id: str,
        prompt: str,
        model: Optional[str],
        effort: Optional[str],
        timeout: int,
        pre_prompt: Optional[str] = None,
    ) -> None:
        """Worker thread executing the turn via provider stream."""
        conv = conv_store.get_conversation(conv_id)
        target_agy_id = conv.get("agy_conversation_id") if conv else None

        # Inject pre-prompt on first turn of conversation or when starting
        effective_prompt = prompt
        if pre_prompt and pre_prompt.strip() and (target_agy_id is None or len(conv.get("messages", [])) <= 1):
            effective_prompt = f"[Consignes système / Pré-prompt de l'utilisateur : {pre_prompt.strip()}]\n\n{prompt}"
            logger.info("Injected pre-prompt for first turn of conversation %s", conv_id)

        logger.info("Turn worker started for conv %s: '%s...'", conv_id, prompt[:40])
        steps_log: List[Dict[str, Any]] = []
        full_text = ""
        final_tokens = None
        final_duration = None
        final_usage = None
        active_provider_id = getattr(provider, "provider_id", "agy")

        # Intercept local slash commands like /usage, /quota, /stats (0 LLM tokens, 0ms latency)
        clean_prompt = prompt.strip().lower()
        if clean_prompt in ("/usage", "à/usage", "/quota", "/stats", "/tokens") or clean_prompt.startswith("/usage "):
            logger.info("Executing local /usage command for conversation %s", conv_id)
            report_text, report_usage = build_usage_report(
                conv_store=conv_store,
                conv_id=conv_id,
                provider=provider,
                model=model,
            )
            time.sleep(0.05)
            turn.emit({"type": "message", "content": report_text})
            conv_store.add_message(
                conv_id=conv_id,
                role="assistant",
                text=report_text,
                tokens=0,
                duration=0.05,
                usage=report_usage,
            )
            turn.emit({
                "type": "done",
                "response": report_text,
                "duration_seconds": 0.05,
                "usage": report_usage,
            })
            turn.status = "done"
            return

        try:
            try:
                stream_iter = provider.process_stream(
                    prompt=effective_prompt,
                    conversation_id=target_agy_id,
                    model=model,
                    effort=effort,
                    timeout=timeout,
                    pre_prompt=pre_prompt,
                    on_proc_started=turn.set_process,
                    cancel_event=turn._cancelled,
                )
            except TypeError:
                stream_iter = provider.process_stream(
                    prompt=effective_prompt,
                    conversation_id=target_agy_id,
                    model=model,
                    effort=effort,
                    dangerously_skip_permissions=True,
                    timeout=timeout,
                    on_proc_started=turn.set_process,
                    cancel_event=turn._cancelled,
                )

            for event in stream_iter:
                if turn.is_cancelled:
                    logger.info("Turn %s marked cancelled during stream; exiting worker loop", conv_id)
                    break

                actual_agy_id = event.get("conversation_id")
                if actual_agy_id:
                    conv_store.set_agy_conversation_id(conv_id, actual_agy_id)

                etype = event.get("type")
                if etype == "cancelled":
                    turn.status = "cancelled"
                    break
                elif etype == "tool_start":
                    steps_log.append({
                        "type": "tool",
                        "tool": event.get("tool"),
                        "parameters": event.get("parameters"),
                        "state": "running",
                    })
                elif etype == "tool_end":
                    tname = event.get("tool")
                    for s in reversed(steps_log):
                        if s.get("type") == "tool" and s.get("tool") == tname and s.get("state") == "running":
                            s["state"] = "done"
                            s["duration"] = event.get("duration", 0)
                            s["output"] = event.get("output", "")
                            break
                elif etype == "text_delta":
                    delta = event.get("delta", "")
                    full_text += delta
                    turn.accumulated_text = full_text
                elif etype == "done":
                    full_text = event.get("response", "") or full_text
                    raw_usage = event.get("usage", {})
                    final_usage = normalize_token_usage(
                        raw_usage=raw_usage,
                        provider_id=active_provider_id,
                        model=model,
                        prompt_text=effective_prompt,
                        response_text=full_text,
                    )
                    final_tokens = final_usage.get("total_tokens")
                    final_duration = event.get("duration_seconds")
                    event["usage"] = final_usage

                turn.steps = steps_log
                turn.broadcast(event)

            # Check if cancelled by user
            if turn.is_cancelled or turn.status == "cancelled":
                turn.status = "cancelled"
                partial_text = full_text.strip()
                notice = "*(Génération interrompue par l'utilisateur)*"
                final_text = f"{partial_text}\n\n{notice}" if partial_text else notice
                assistant_msg = conv_store.add_message(
                    conv_id=conv_id,
                    role="assistant",
                    text=final_text,
                    steps=steps_log,
                )
                turn.result = assistant_msg
                logger.info("Turn cancelled for conv %s (saved partial message, %d chars)", conv_id, len(final_text))
                turn.broadcast({
                    "type": "cancelled",
                    "message": "Génération interrompue par l'utilisateur",
                    "assistant_message": assistant_msg,
                    "conversation": conv_store.get_conversation(conv_id),
                })
                return

            # Persist assistant message even if all web clients disconnected!
            if full_text.strip():
                if final_usage is None:
                    final_usage = normalize_token_usage(
                        raw_usage={},
                        provider_id=active_provider_id,
                        model=model,
                        prompt_text=effective_prompt,
                        response_text=full_text,
                    )
                    final_tokens = final_usage.get("total_tokens")

                assistant_msg = conv_store.add_message(
                    conv_id=conv_id,
                    role="assistant",
                    text=full_text,
                    tokens=final_tokens,
                    duration=final_duration,
                    steps=steps_log,
                    usage=final_usage,
                )
                turn.result = assistant_msg
                logger.info("Turn completed for conv %s (saved %d chars)", conv_id, len(full_text))
                turn.broadcast({
                    "type": "finished",
                    "message": assistant_msg,
                    "conversation": conv_store.get_conversation(conv_id),
                })
                turn.status = "completed"
            else:
                err_text = "L'assistant n'a renvoyé aucune réponse."
                assistant_msg = conv_store.add_message(
                    conv_id=conv_id,
                    role="assistant",
                    text=f"⚠️ {err_text}",
                    steps=steps_log,
                )
                turn.status = "error"
                turn.error = err_text
                turn.broadcast({
                    "type": "error",
                    "error": err_text,
                    "message": assistant_msg,
                })

        except Exception as err:
            if turn.is_cancelled or turn.status == "cancelled":
                return
            logger.exception("Turn worker exception for conv %s: %s", conv_id, err)
            err_msg = f"Erreur lors de l'exécution : {err}"
            turn.status = "error"
            turn.error = str(err)
            conv_store.add_message(
                conv_id=conv_id,
                role="assistant",
                text=f"⚠️ {err_msg}",
                steps=steps_log,
            )
            turn.broadcast({"type": "error", "error": err_msg})
        finally:
            with self._lock:
                if turn.status == "running":
                    turn.status = "completed"
