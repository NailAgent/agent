from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from agent.agents.schema import BookingSlots
from agent.tools.conversation_store import ConversationStateStore


def test_conversation_store_roundtrip(tmp_path: Path) -> None:
    store = ConversationStateStore(state_path=tmp_path / "conversation_state.json")
    slots = BookingSlots(
        name="김지수",
        phone_num="010-1234-5678",
        off_removal=True,
        reserve_date="2026-05-20",
        reserve_time="17:00",
        service_code="GEL_NAIL",
        past_visit=False,
    )

    store.save(
        "thread-1",
        {
            "intent": "booking",
            "slots": slots,
            "pending_intent": "booking",
            "pending_missing_fields": ["name"],
            "pending_followup_question": "성함을 알려주세요.",
            "booking_status": "N/A",
            "next_action": "ask_followup",
        },
    )

    loaded = store.load("thread-1")

    assert loaded["intent"] == "booking"
    assert loaded["pending_intent"] == "booking"
    assert loaded["pending_missing_fields"] == ["name"]
    assert loaded["pending_followup_question"] == "성함을 알려주세요."
    assert loaded["slots"].name == "김지수"
    assert loaded["slots"].phone_num == "010-1234-5678"

    store.update("thread-1", {"booking_status": "payment_confirmed"})
    updated = store.load("thread-1")
    assert updated["booking_status"] == "payment_confirmed"
