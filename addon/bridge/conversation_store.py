"""Conversation storage manager for Chassitant Chatbot.

Persists conversation threads, titles, and message histories to disk (JSON).
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("chassitant.conversations")

CONVERSATIONS_FILE_NAME = "conversations.json"


class ConversationStore:
    """Manages persistent conversation threads on disk."""

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        if data_dir is None:
            data_env = os.getenv("CHASSITANT_DATA_DIR")
            if data_env and Path(data_env).is_dir():
                data_dir = Path(data_env)
            else:
                data_dir = Path(__file__).resolve().parent.parent

        self.data_dir = data_dir
        self.file_path = self.data_dir / CONVERSATIONS_FILE_NAME
        self._conversations: Dict[str, Dict[str, Any]] = {}
        self.load()

    def load(self) -> None:
        """Load conversations from disk."""
        if self.file_path.exists():
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    self._conversations = json.load(f)
                return
            except Exception as err:
                logger.warning("Failed to load conversations from %s: %s", self.file_path, err)
        self._conversations = {}

    def save(self) -> None:
        """Persist conversations to disk."""
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self._conversations, f, ensure_ascii=False, indent=2)
        except Exception as err:
            logger.error("Failed to save conversations to %s: %s", self.file_path, err)

    def list_conversations(self) -> List[Dict[str, Any]]:
        """Return list of all conversations sorted by updated_at (newest first)."""
        result = []
        for conv_id, data in self._conversations.items():
            messages = data.get("messages", [])
            last_message = messages[-1]["text"] if messages else ""
            last_usage = None
            for m in reversed(messages):
                if m.get("role") == "assistant" and m.get("usage"):
                    last_usage = m["usage"]
                    break
            result.append(
                {
                    "id": conv_id,
                    "agy_conversation_id": data.get("agy_conversation_id"),
                    "title": data.get("title", "Nouvelle discussion"),
                    "created_at": data.get("created_at", time.time()),
                    "updated_at": data.get("updated_at", time.time()),
                    "message_count": len(messages),
                    "last_message_preview": (last_message[:60] + "...") if len(last_message) > 60 else last_message,
                    "last_usage": last_usage,
                }
            )
        result.sort(key=lambda c: c["updated_at"], reverse=True)
        return result

    def get_conversation(self, conv_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve full conversation thread with messages."""
        return self._conversations.get(conv_id)

    def create_conversation(self, title: Optional[str] = None, conv_id: Optional[str] = None) -> Dict[str, Any]:
        """Create a new conversation thread."""
        conv_id = conv_id or str(uuid.uuid4())
        now = time.time()
        record = {
            "id": conv_id,
            "agy_conversation_id": None,
            "title": title or "Nouvelle discussion",
            "created_at": now,
            "updated_at": now,
            "messages": [],
        }
        self._conversations[conv_id] = record
        self.save()
        return record

    def set_agy_conversation_id(self, conv_id: str, agy_conv_id: str) -> None:
        """Associate an internal conversation thread with agy's underlying conversation ID."""
        if conv_id in self._conversations and agy_conv_id:
            if self._conversations[conv_id].get("agy_conversation_id") != agy_conv_id:
                self._conversations[conv_id]["agy_conversation_id"] = agy_conv_id
                self.save()

    def rename_conversation(self, conv_id: str, new_title: str) -> bool:
        """Update conversation title."""
        if conv_id in self._conversations:
            self._conversations[conv_id]["title"] = new_title.strip()
            self._conversations[conv_id]["updated_at"] = time.time()
            self.save()
            return True
        return False

    def delete_conversation(self, conv_id: str) -> bool:
        """Delete conversation thread."""
        if conv_id in self._conversations:
            del self._conversations[conv_id]
            self.save()
            return True
        return False

    def add_message(
        self,
        conv_id: str,
        role: str,
        text: str,
        tokens: Optional[int] = None,
        duration: Optional[float] = None,
        steps: Optional[List[Dict[str, Any]]] = None,
        usage: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Add a message to a conversation thread."""
        if conv_id not in self._conversations:
            self.create_conversation(conv_id=conv_id)

        conv = self._conversations[conv_id]
        msg = {
            "id": str(uuid.uuid4()),
            "role": role,  # 'user' or 'assistant'
            "text": text,
            "timestamp": time.time(),
            "tokens": tokens,
            "duration": duration,
            "steps": steps or [],
            "usage": usage,
        }
        conv["messages"].append(msg)
        conv["updated_at"] = time.time()

        # Auto-generate title from the first user message if still default
        if conv.get("title") in ("Nouvelle discussion", None) and role == "user":
            clean_title = text.strip().split("\n")[0][:40]
            if clean_title:
                conv["title"] = clean_title

        self.save()
        return msg
