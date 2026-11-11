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
from typing import Any, Dict, List, Optional

logger = logging.getLogger("chassitant.turn_manager")


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
                    final_tokens = event.get("usage", {}).get("total_tokens")
                    final_duration = event.get("duration_seconds")

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
                assistant_msg = conv_store.add_message(
                    conv_id=conv_id,
                    role="assistant",
                    text=full_text,
                    tokens=final_tokens,
                    duration=final_duration,
                    steps=steps_log,
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
