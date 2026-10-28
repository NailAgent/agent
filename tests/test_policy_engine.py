"""PolicyEngine의 지난 날짜·시각 검사 (한국 시각 기준).

기준 시각을 now 인자로 고정해서, 테스트를 언제 돌려도 결과가 같다.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from agent.tools.policy_engine import PolicyEngine

KST = PolicyEngine.SHOP_TZ
NOW = datetime(2026, 10, 28, 10, 49, tzinfo=KST)  # 수요일 오전 10:49
BUSINESS_HOURS = {"start": "10:00", "end": "21:00"}


def validate(date_str: str, time_str: str, now: datetime | None = NOW, booked: list | None = None) -> dict:
    return PolicyEngine.validate_reservation(
        date_str,
        time_str,
        60,
        booked or [],
        business_hours=BUSINESS_HOURS,
        closed_days=1,  # 백엔드 값 1 = 월요일 휴무
        now=now,
    )


# ---------- 예약 가능 여부 ----------
def test_past_date_is_rejected() -> None:
    result = validate("2026-10-21", "16:00")
    assert result == {"valid": False, "reason": "이미 지난 날짜입니다."}


def test_earlier_time_today_is_rejected() -> None:
    result = validate("2026-10-28", "10:00")
    assert result == {"valid": False, "reason": "이미 지난 시간입니다."}


def test_current_minute_is_rejected() -> None:
    assert validate("2026-10-28", "10:49")["reason"] == "이미 지난 시간입니다."


def test_later_time_today_is_allowed() -> None:
    assert validate("2026-10-28", "15:00")["valid"] is True


def test_future_date_is_allowed() -> None:
    assert validate("2026-10-29", "10:00")["valid"] is True


def test_past_check_comes_before_closed_day() -> None:
    # 2026-10-26은 지난 월요일. 휴무일보다 지난 날짜라는 안내가 먼저다
    assert validate("2026-10-26", "14:00")["reason"] == "이미 지난 날짜입니다."


def test_uses_korea_date_even_when_now_is_utc() -> None:
    now_utc = datetime(2026, 10, 27, 16, 30, tzinfo=timezone.utc)  # 한국 시각 10/28 01:30
    assert validate("2026-10-27", "15:00", now=now_utc)["reason"] == "이미 지난 날짜입니다."
    assert validate("2026-10-28", "11:00", now=now_utc)["valid"] is True


def test_naive_now_is_treated_as_korea_time() -> None:
    naive = datetime(2026, 10, 28, 10, 49)
    assert validate("2026-10-28", "10:30", now=naive)["reason"] == "이미 지난 시간입니다."
    assert validate("2026-10-28", "11:00", now=naive)["valid"] is True


def test_default_now_is_korea_time() -> None:
    assert PolicyEngine.now().utcoffset() == timedelta(hours=9)


def test_existing_rules_still_apply_to_future_dates() -> None:
    assert validate("2026-11-02", "14:00")["reason"] == "해당 요일은 휴무일입니다."  # 월요일
    assert "영업시간" in validate("2026-10-29", "20:30")["reason"]
    booked = [{"start": "14:00", "end": "15:00"}]
    assert validate("2026-10-29", "14:30", booked=booked)["reason"] == "해당 시간에는 이미 예약이 있습니다."


# ---------- 휴무일 (백엔드 closed_days 값 → 요일) ----------
def closed_reason(date_str: str, closed_days) -> str:
    result = PolicyEngine.validate_reservation(
        date_str, "14:00", 60, [], business_hours=BUSINESS_HOURS, closed_days=closed_days, now=NOW
    )
    return result["reason"]


CLOSED = "해당 요일은 휴무일입니다."


def test_backend_value_1_means_monday() -> None:
    assert closed_reason("2026-11-02", 1) == CLOSED  # 월요일
    assert closed_reason("2026-11-03", 1) != CLOSED  # 화요일


def test_sunday_is_read_the_same_from_0_or_7() -> None:
    assert closed_reason("2026-11-01", 0) == CLOSED  # 일요일 (JavaScript getDay 방식)
    assert closed_reason("2026-11-01", 7) == CLOSED  # 일요일 (ISO 방식)
    assert closed_reason("2026-11-02", 7) != CLOSED


def test_multiple_closed_days() -> None:
    assert closed_reason("2026-11-01", [7, 1]) == CLOSED
    assert closed_reason("2026-11-02", [7, 1]) == CLOSED
    assert closed_reason("2026-11-03", [7, 1]) != CLOSED


def test_missing_closed_days_falls_back_to_monday() -> None:
    assert closed_reason("2026-11-02", None) == CLOSED
    assert closed_reason("2026-11-03", None) != CLOSED


def test_closed_day_names() -> None:
    assert PolicyEngine.closed_day_names(1) == "월요일"
    assert PolicyEngine.closed_day_names([7, 1]) == "월요일, 일요일"


def test_inquiry_context_shows_backend_closed_day() -> None:
    from agent.agents.inquiry_agent import _format_shop_context

    context = _format_shop_context({"closed_days": 1})
    assert "- 정기휴무: 월요일" in context


# ---------- 추천 시간대 ----------
def test_recommendations_without_date_are_unchanged() -> None:
    assert PolicyEngine.get_available_recommendations(BUSINESS_HOURS, [], 60) == ["10:00", "10:30", "11:00"]


def test_recommendations_today_skip_past_times() -> None:
    recs = PolicyEngine.get_available_recommendations(BUSINESS_HOURS, [], 60, date_str="2026-10-28", now=NOW)
    assert recs == ["11:00", "11:30", "12:00"]


def test_recommendations_today_skip_past_times_around_bookings() -> None:
    booked = [{"start": "11:00", "end": "12:30"}]
    recs = PolicyEngine.get_available_recommendations(BUSINESS_HOURS, booked, 60, date_str="2026-10-28", now=NOW)
    assert recs == ["12:30", "13:00", "13:30"]


def test_recommendations_for_past_date_are_empty() -> None:
    assert PolicyEngine.get_available_recommendations(BUSINESS_HOURS, [], 60, date_str="2026-10-21", now=NOW) == []


def test_recommendations_for_future_date_start_at_opening() -> None:
    recs = PolicyEngine.get_available_recommendations(BUSINESS_HOURS, [], 60, date_str="2026-10-29", now=NOW)
    assert recs == ["10:00", "10:30", "11:00"]
