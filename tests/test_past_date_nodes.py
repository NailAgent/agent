"""예약·변경 노드가 지난 날짜·시각과 휴무일을 백엔드에 쓰기 전에 거절하는지.

백엔드 호출은 가짜 함수로 바꾸고, 현재 시각은 PolicyEngine.now를 고정해서 언제 돌려도 결과가 같다.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# nodes 모듈은 import할 때 LLM 클라이언트를 만든다. 이 테스트는 LLM을 호출하지 않는다.
os.environ.setdefault("OPENAI_API_KEY", "test-dummy")

from agent.agents.schema import BookingSlots
from agent.graph import nodes
from agent.tools.policy_engine import PolicyEngine

NOW = datetime(2026, 10, 28, 10, 49, tzinfo=PolicyEngine.SHOP_TZ)  # 수요일 오전 10:49
SHOP_INFO = {"success": True, "deposit_amount": 5000, "closed_days": 1, "service_durations": None}  # 1 = 월요일 휴무
EXISTING_RESERVATION = {
    "id": 1,
    "name": "남민서",
    "phone_num": "010-1111-2222",
    "reserve_date": "2026-11-05",
    "reserve_time": "14:00-15:00",
    "service": "젤네일",
    "off_removal": False,
    "visit_status": "PENDING",
}


def fake_schedule(date_str: str) -> dict:
    return {"success": True, "source": "test", "business_hours": {"start": "10:00", "end": "21:00"}, "booked_slots": []}


@pytest.fixture
def backend(monkeypatch: pytest.MonkeyPatch) -> dict:
    calls: dict[str, list] = {"create": [], "update": []}
    monkeypatch.setattr(PolicyEngine, "now", classmethod(lambda cls: NOW))
    client = nodes.backend_client
    monkeypatch.setattr(client, "get_shop_info", lambda: SHOP_INFO)
    monkeypatch.setattr(client, "get_schedule", fake_schedule)
    monkeypatch.setattr(
        client,
        "create_reservation",
        lambda payload: calls["create"].append(payload) or {"success": True, "response": {"data": {"id": 99}}},
    )
    monkeypatch.setattr(client, "find_reservations", lambda **kwargs: [dict(EXISTING_RESERVATION)])
    monkeypatch.setattr(
        client,
        "update_reservation",
        lambda reservation_id, payload: calls["update"].append((reservation_id, payload)) or {"success": True},
    )
    return calls


def booking_state(reserve_date: str, reserve_time: str) -> dict:
    slots = BookingSlots(
        name="테스트",
        phone_num="010-0000-0001",
        off_removal=False,
        reserve_date=reserve_date,
        reserve_time=reserve_time,
        service_code="GEL_NAIL",
        past_visit=False,
    )
    return {"intent": "booking", "slots": slots, "user_input": ""}


def change_state(user_input: str) -> dict:
    return {"intent": "change", "slots": BookingSlots(name="남민서"), "user_input": user_input}


# ---------- 예약 ----------
def test_booking_past_date_is_rejected_without_creating(backend: dict) -> None:
    result = nodes.booking_node(booking_state("2026-10-21", "16:00"))
    assert result["booking_status"] == "rejected"
    assert "이미 지난 날짜입니다." in result["response_draft"]
    assert backend["create"] == []


def test_booking_earlier_time_today_recommends_only_later_times(backend: dict) -> None:
    result = nodes.booking_node(booking_state("2026-10-28", "10:00"))
    assert result["booking_status"] == "rejected"
    assert "이미 지난 시간입니다." in result["response_draft"]
    assert "• 11:00" in result["response_draft"]
    assert "• 10:00" not in result["response_draft"]
    assert backend["create"] == []


def test_booking_later_time_today_is_created(backend: dict) -> None:
    result = nodes.booking_node(booking_state("2026-10-28", "15:00"))
    assert result["booking_status"] != "rejected"
    assert len(backend["create"]) == 1
    assert backend["create"][0]["reserve_date"] == "2026-10-28"


# ---------- 변경 ----------
def test_change_to_past_date_is_rejected_without_updating(backend: dict) -> None:
    result = nodes.change_node(change_state("남민서 2026-11-05 14:00 2026-10-21 16:00 젤네일 예약 변경하고 싶어요"))
    assert result["booking_status"] == "rejected"
    assert "이미 지난 날짜입니다." in result["response_draft"]
    assert backend["update"] == []


def test_change_to_future_date_is_updated(backend: dict) -> None:
    result = nodes.change_node(change_state("남민서 2026-11-05 14:00 2026-11-06 16:00 젤네일 예약 변경하고 싶어요"))
    assert result["booking_status"] == "updated"
    assert backend["update"] == [(1, {"reserve_date": "2026-11-06", "reserve_time": "16:00-17:00", "estimated_duration_min": 60})]


# ---------- 휴무일 ----------
def test_booking_on_closed_monday_is_rejected(backend: dict) -> None:
    result = nodes.booking_node(booking_state("2026-11-02", "16:00"))  # 월요일
    assert result["booking_status"] == "rejected"
    assert "휴무일" in result["response_draft"]
    assert backend["create"] == []


def test_booking_on_tuesday_is_created(backend: dict) -> None:
    result = nodes.booking_node(booking_state("2026-11-03", "16:00"))  # 화요일
    assert result["booking_status"] != "rejected"
    assert len(backend["create"]) == 1


def test_change_uses_closed_day_from_shop_info(backend: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(nodes.backend_client, "get_shop_info", lambda: {**SHOP_INFO, "closed_days": 3})  # 수요일 휴무
    result = nodes.change_node(change_state("남민서 2026-11-05 14:00 2026-11-04 16:00 젤네일 예약 변경하고 싶어요"))
    assert result["booking_status"] == "rejected"
    assert "휴무일" in result["response_draft"]
    assert "추천 가능한 시간대를 찾지 못했습니다." in result["response_draft"]  # 휴무일에는 시간을 추천하지 않는다
    assert backend["update"] == []
