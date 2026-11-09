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
        self.status = "running"  # "running", "completed", "error"
        self.steps: List[Dict[str, Any]] = []
        self.accumulated_text = ""
        self.result: Optional[Dict[str, Any]] = None
        self.error: Optional[str] = None
        self._subscribers: List[queue.Queue] = []
        self._lock = threading.Lock()

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

    def start_turn(
        self,
        conv_id: str,
        prompt: str,
        agy_client: Any,
        conv_store: Any,
        model: Optional[str] = None,
        effort: Optional[str] = None,
        timeout: int = 300,
    ) -> ActiveTurn:
        """Start a new background turn for a conversation."""
        with self._lock:
            existing = self._turns.get(conv_id)
            if existing and existing.status == "running":
                return existing

            turn = ActiveTurn(conv_id, prompt)
            self._turns[conv_id] = turn

        thread = threading.Thread(
            target=self._run_worker,
            args=(turn, agy_client, conv_store, conv_id, prompt, model, effort, timeout),
            daemon=True,
            name=f"TurnWorker-{conv_id[:8]}",
        )
        thread.start()
        return turn

    def _run_worker(
        self,
        turn: ActiveTurn,
        agy_client: Any,
        conv_store: Any,
        conv_id: str,
        prompt: str,
        model: Optional[str],
        effort: Optional[str],
        timeout: int,
    ) -> None:
        """Worker thread executing the turn via agy stream."""
        conv = conv_store.get_conversation(conv_id)
        target_agy_id = conv.get("agy_conversation_id") if conv else None
        logger.info("Turn worker started for conv %s (agy_id=%s): '%s...'", conv_id, target_agy_id, prompt[:40])
        steps_log: List[Dict[str, Any]] = []
        full_text = ""
        final_tokens = None
        final_duration = None

        try:
            for event in agy_client.process_stream(
                prompt=prompt,
                conversation_id=target_agy_id,
                model=model,
                effort=effort,
                dangerously_skip_permissions=True,
                timeout=timeout,
            ):
                actual_agy_id = event.get("conversation_id")
                if actual_agy_id:
                    conv_store.set_agy_conversation_id(conv_id, actual_agy_id)

                etype = event.get("type")
                if etype == "tool_start":
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
                turn.status = "completed"
                turn.result = assistant_msg
                logger.info("Turn completed for conv %s (saved %d chars)", conv_id, len(full_text))
                turn.broadcast({
                    "type": "finished",
                    "message": assistant_msg,
                    "conversation": conv_store.get_conversation(conv_id),
                })
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
            turn.status = "completed"
