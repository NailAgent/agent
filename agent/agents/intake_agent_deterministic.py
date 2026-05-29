"""Deterministic (keyword/regex) fallback for IntakeAgent when LLM is unavailable."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Optional

from agent.agents.schema import BookingSlots, Intent, IntakeResult


def _extract_first(pattern: str, text: str, flags: int = re.IGNORECASE) -> Optional[str]:
    match = re.search(pattern, text, flags)
    if not match:
        return None
    return match.group(1).strip()


def _normalize_phone(phone: Optional[str]) -> Optional[str]:
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 11 and digits.startswith("010"):
        return f"{digits[:3]}-{digits[3:7]}-{digits[7:]}"
    return phone if "-" in phone else None


def _parse_bool_from_text(text: str, positive_patterns: list[str], negative_patterns: list[str]) -> Optional[bool]:
    lowered = text.lower()
    for pattern in negative_patterns:
        if pattern in lowered:
            return False
    for pattern in positive_patterns:
        if pattern in lowered:
            return True
    return None


def _resolve_relative_date(text: str) -> Optional[str]:
    today = datetime.now().date()
    normalized = text.replace(" ", "")
    relative_map = {"오늘": 0, "내일": 1, "모레": 2}
    for keyword, delta in relative_map.items():
        if keyword in normalized:
            return (today + timedelta(days=delta)).strftime("%Y-%m-%d")
    return _extract_first(r"(\d{4}-\d{2}-\d{2})", text)


def _normalize_service_code(text: str) -> Optional[str]:
    normalized = text.replace(" ", "")
    if any(k in normalized for k in ("페디큐어", "페디")):
        return "PEDICURE"
    if any(k in normalized for k in ("기본네일", "손톱케어", "기본케어", "케어")):
        return "GEL_BASIC"
    if "젤" in normalized:
        return "GEL_NAIL"
    return None


def _classify_intent(text: str) -> Intent:
    normalized = text.replace(" ", "")
    if any(k in normalized for k in ("예약변경", "바꾸고싶", "변경", "수정")):
        return Intent.CHANGE
    if any(k in normalized for k in ("예약취소", "취소하고싶", "취소")):
        return Intent.CANCEL
    if any(k in normalized for k in ("입금", "결제", "송금", "환불")):
        return Intent.PAYMENT
    if any(k in normalized for k in ("예약문의", "예약가능", "예약하고싶", "예약잡고", "애약문의")):
        return Intent.BOOKING
    if any(k in normalized for k in ("안녕", "저기요", "안녕하세요", "하이", "hello")):
        return Intent.GREETING
    if "예약" in normalized:
        return Intent.BOOKING
    if any(k in normalized for k in ("가격", "영업시간", "위치", "주차", "메뉴", "시술", "얼마")):
        return Intent.INQUIRY
    return Intent.UNKNOWN


def _extract_name(text: str) -> Optional[str]:
    for pattern in (
        r"(?:성함|이름|예약자)\s*[:：]?\s*([가-힣]{2,4})",
        r"([가-힣]{2,4})\s*(?:님)?\s*010-?\d{3,4}-?\d{4}",
        r"^([가-힣]{2,4})\s+(?:\d{4}-\d{2}-\d{2}|01\d-\d{3,4}-\d{4})",
        r"^([가-힣]{2,4})\s+.*?(?:예약|입금|취소|변경)",
        r"성함\s*[:：]?\s*([가-힣]{2,4})",
    ):
        value = _extract_first(pattern, text)
        if value:
            return value
    return None


def _extract_phone(text: str) -> Optional[str]:
    return _normalize_phone(_extract_first(r"(01[016789]-?\d{3,4}-?\d{4})", text))


def _extract_time(text: str) -> Optional[str]:
    value = _extract_first(r"(\d{1,2}:\d{2})", text)
    if not value:
        m = re.search(r"(오전|오후)?\s*(\d{1,2})\s*시", text)
        if not m:
            return None
        meridiem, hour = m.group(1), int(m.group(2))
        if meridiem == "오후" and hour < 12:
            hour += 12
        if meridiem == "오전" and hour == 12:
            hour = 0
        return f"{hour:02d}:00"
    hour, minute = value.split(":")
    return f"{int(hour):02d}:{int(minute):02d}"


def _extract_off_removal(text: str) -> Optional[bool]:
    explicit = _extract_first(r"(?:젤제거\s*유무|젤제거|오프\s*제거)\s*[:：]?\s*([OXox])", text)
    if explicit:
        return explicit.upper() == "O"
    result = _parse_bool_from_text(
        text,
        positive_patterns=["제거o", "제거있", "오프있", "off있", "있어요", "함", "o"],
        negative_patterns=["제거x", "제거없", "오프없", "없어요", "안해", "x", "no"],
    )
    if result is not None:
        return result
    normalized = text.replace(" ", "")
    if "제거" in normalized or "오프" in normalized:
        return not any(k in normalized for k in ("없", "안", "x"))
    return None


def _extract_past_visit(text: str) -> Optional[bool]:
    explicit = _extract_first(r"(?:과거\s*방문경험|방문경험)\s*[:：]?\s*([OXox])", text)
    if explicit:
        return explicit.upper() == "O"
    normalized = text.replace(" ", "").lower()
    if any(k in normalized for k in ("처음가", "첫방문", "처음방문", "처음가요", "첫방")):
        return False
    if any(k in normalized for k in ("재방문", "방문경험", "가본적", "다시")):
        return not any(k in normalized for k in ("없", "x", "처음"))
    return None


def deterministic_intake(user_input: str, build_followup_fn) -> IntakeResult:
    """Keyword/regex-based intake — runs when LLM is unavailable."""
    intent = _classify_intent(user_input)
    slots = BookingSlots()
    missing_fields: list[str] = []
    need_followup = False
    followup_question: Optional[str] = None

    if intent == Intent.BOOKING:
        slots.name = _extract_name(user_input)
        slots.phone_num = _extract_phone(user_input)
        slots.off_removal = _extract_off_removal(user_input)
        slots.reserve_date = _resolve_relative_date(user_input)
        slots.reserve_time = _extract_time(user_input)
        slots.service_code = _normalize_service_code(user_input)
        slots.past_visit = _extract_past_visit(user_input)

        required = {
            "name": slots.name, "phone_num": slots.phone_num,
            "off_removal": slots.off_removal, "reserve_date": slots.reserve_date,
            "reserve_time": slots.reserve_time, "service_code": slots.service_code,
            "past_visit": slots.past_visit,
        }
        missing_fields = [f for f, v in required.items() if v is None]
        need_followup = bool(missing_fields)
        if need_followup:
            followup_question = build_followup_fn(missing_fields)

    elif intent == Intent.UNKNOWN:
        need_followup = True
        followup_question = "예약 문의, 예약 변경, 예약 취소, 입금 확인 중 어떤 요청인지 알려주세요."

    return IntakeResult(
        intent=intent,
        slots=slots,
        missing_fields=missing_fields,
        uncertain_fields=[],
        need_followup=need_followup,
        followup_question=followup_question,
    )
