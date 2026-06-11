from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent.agents.schema import BookingSlots

_PERSISTED_KEYS = (
    "intent",
    "slots",
    "missing_fields",
    "kakao_user_id",
    "plusfriend_user_key",
    "pending_intent",
    "pending_missing_fields",
    "pending_followup_question",
    "designer",
    "is_bookable",
    "booking_status",
    "next_action",
    "booking_id",
    "order_id",
)


class ConversationStateStore:
    """Tiny file-backed state store for preserving chat context between requests."""

    def __init__(self, state_path: Path | None = None):
        project_root = Path(__file__).resolve().parents[2]
        self.state_path = state_path or (project_root / ".runtime" / "conversation_state.json")
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def load(self, thread_id: str) -> dict[str, Any]:
        if not thread_id:
            return {}

        with self._lock:
            data = self._read_all()

        raw_state = data.get(thread_id)
        if not isinstance(raw_state, dict):
            return {}
        return self._deserialize_state(raw_state)

    def save(self, thread_id: str, state: dict[str, Any]) -> None:
        if not thread_id:
            return

        payload = self._serialize_state(state)
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()

        with self._lock:
            data = self._read_all()
            data[thread_id] = payload
            self._write_all(data)

    def update(self, thread_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        state = self.load(thread_id)
        state.update(updates)
        self.save(thread_id, state)
        return state

    def clear(self, thread_id: str) -> None:
        if not thread_id:
            return

        with self._lock:
            data = self._read_all()
            if thread_id in data:
                data.pop(thread_id, None)
                self._write_all(data)

    def _read_all(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {}
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _write_all(self, data: dict[str, Any]) -> None:
        temp_path = self.state_path.with_suffix(".tmp")
        temp_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temp_path.replace(self.state_path)

    def _serialize_state(self, state: dict[str, Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for key in _PERSISTED_KEYS:
            if key in state:
                payload[key] = self._serialize_value(state[key])
        return payload

    def _deserialize_state(self, state: dict[str, Any]) -> dict[str, Any]:
        payload = dict(state)
        slots = payload.get("slots")
        if isinstance(slots, dict):
            try:
                payload["slots"] = BookingSlots(**slots)
            except Exception:
                payload["slots"] = None
        return payload

    def _serialize_value(self, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, list):
            return [self._serialize_value(item) for item in value]
        if isinstance(value, dict):
            return {str(key): self._serialize_value(item) for key, item in value.items()}
        if hasattr(value, "model_dump"):
            return value.model_dump()
        if hasattr(value, "dict"):
            return value.dict()
        return str(value)
