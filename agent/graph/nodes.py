from __future__ import annotations

import os
import re
from datetime import datetime, timedelta
from urllib.parse import urlencode

from agent.agents.constants import (
    BOOKING_FORM_GUIDE,
    BOOKING_MISSING_DATETIME_MESSAGE,
    CANCEL_MESSAGE,
    CHANGE_MESSAGE,
    INQUIRY_FALLBACK_MESSAGE,
    PAYMENT_MESSAGE,
    UNKNOWN_FALLBACK_MESSAGE,
    WELCOME_MESSAGE,
)
from agent.agents.intake_agent import IntakeAgent, _build_followup_question
from agent.agents.inquiry_agent import InquiryAgent
from agent.agents.schema import BookingSlots
from agent.graph.state import ReservationState, merge_slots
from agent.tools.backend_client import BackendClient
from agent.tools.policy_engine import PolicyEngine

intake_agent = IntakeAgent()
inquiry_agent = InquiryAgent()
backend_client = BackendClient()

_FOLLOWUP_FALLBACK_INTENTS = {"unknown"}

_AFFIRMATIVE_KEYWORDS = {"맞아요", "맞습니다", "네", "예", "응", "맞아", "그렇습니다", "그래요", "yes", "ㅇㅇ", "ㅇ"}
_NEGATIVE_KEYWORDS = {"아니요", "아니에요", "아닌데요", "틀려요", "아니", "아님", "no", "다른거", "다른예약"}


def _is_affirmative(text: str) -> bool:
    t = text.strip().lower().replace(" ", "")
    return any(k in t for k in _AFFIRMATIVE_KEYWORDS)


def _is_negative(text: str) -> bool:
    t = text.strip().lower().replace(" ", "")
    return any(k in t for k in _NEGATIVE_KEYWORDS)


def _pick_nearest_future(candidates: list[dict]) -> dict | None:
    """미래 예약 중 가장 최근에 생성된 1건 반환 (취소된 건 제외)."""
    from datetime import date
    today = date.today().isoformat()
    future = [
        c for c in candidates
        if str(c.get("reserve_date", "")) >= today
        and str(c.get("visit_status", "")).upper() != "CANCELLED"
    ]
    if not future:
        return None
    return sorted(future, key=lambda c: c.get("id", 0), reverse=True)[0]


def _build_cancel_confirmation_message(reservation: dict) -> str:
    name = reservation.get("name", "")
    date = reservation.get("reserve_date", "")
    time = reservation.get("reserve_time", "")
    service = reservation.get("service", "")
    lines = [f"{name}님의 최근 예약 정보입니다.", "", f"📅 {date} {time}"]
    if service:
        lines.append(f"💅 {service}")
    lines.extend(["", "이 예약을 취소해드릴까요? (맞아요 / 아니요)"])
    return "\n".join(lines)


def _intent_to_str(intent) -> str:
    """Enum 또는 문자열 intent를 plain string으로 정규화."""
    return intent.value if hasattr(intent, "value") else str(intent or "")


def _pending_state_update(intent: str, missing_fields: list[str] | None = None, followup_question: str | None = None) -> dict:
    return {
        "pending_intent": intent,
        "pending_missing_fields": missing_fields or [],
        "pending_followup_question": followup_question,
    }


def _clear_pending_state() -> dict:
    return {
        "pending_intent": None,
        "pending_missing_fields": [],
        "pending_followup_question": None,
    }


def _should_inherit_pending_intent(state: ReservationState, current_intent: str) -> bool:
    if not state.get("pending_intent"):
        return False
    if current_intent in _FOLLOWUP_FALLBACK_INTENTS:
        return True
    # Slot-like inputs (date/time) are often misclassified as booking during a change flow
    if current_intent == "booking" and state.get("pending_intent") == "change":
        return True
    return False


def _resolve_intent_with_pending(state: ReservationState, current_intent: str) -> str:
    if _should_inherit_pending_intent(state, current_intent):
        return str(state.get("pending_intent"))
    return current_intent


def build_non_booking_response(intent: str) -> str:
    """예약 외 intent에 대한 v1 고정 응답 반환."""

    responses = {
        "greeting": WELCOME_MESSAGE,
        "inquiry": INQUIRY_FALLBACK_MESSAGE,
        "change": CHANGE_MESSAGE,
        "cancel": CANCEL_MESSAGE,
        "payment": PAYMENT_MESSAGE,
        "unknown": UNKNOWN_FALLBACK_MESSAGE,
    }
    return responses.get(intent, UNKNOWN_FALLBACK_MESSAGE)


def _get_service_display_name(service_code: str) -> str:
    """서비스 코드를 한국어 명칭으로 변환 (백엔드 검색용)."""
    service_map = {
        "GEL_BASIC": "기본네일",
        "GEL_NAIL": "젤네일",
        "PEDICURE": "페디큐어",
    }
    return service_map.get(service_code, service_code)


def _candidate_summary_lines(candidates: list[dict]) -> str:
    """예약 후보 목록을 불릿 텍스트로 포맷 (최대 3건)."""
    if not candidates:
        return ""
    return "\n".join(f"- {backend_client.format_reservation_summary(item)}" for item in candidates[:3])


def _resolve_shop_text(shop_info: dict, key: str, fallback: str) -> str:
    """shop_info에서 특정 텍스트 키를 읽되, 없으면 fallback 반환."""
    value = shop_info.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


_RELATIVE_DATE_OFFSETS = {"오늘": 0, "내일": 1, "모레": 2}


def _service_code_from_display_name(service_name: str | None) -> str | None:
    if not service_name:
        return None

    normalized = service_name.replace(" ", "")
    service_map = {
        "기본네일": "GEL_BASIC",
        "기본케어": "GEL_BASIC",
        "손톱케어": "GEL_BASIC",
        "젤네일": "GEL_NAIL",
        "페디큐어": "PEDICURE",
        "페디": "PEDICURE",
    }
    for keyword, code in service_map.items():
        if keyword in normalized:
            return code
    return None


def _resolve_relative_date_token(token: str) -> str:
    if token in _RELATIVE_DATE_OFFSETS:
        return (datetime.now().date() + timedelta(days=_RELATIVE_DATE_OFFSETS[token])).strftime("%Y-%m-%d")
    return token


def _weekday_korean(date_str: str | None) -> str:
    if not date_str:
        return ""
    try:
        weekday_map = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
        weekday = datetime.strptime(date_str, "%Y-%m-%d").weekday()
        return weekday_map[weekday]
    except Exception:
        return ""


def _extract_date_tokens(text: str) -> list[str]:
    normalized = text.replace(" ", "")
    tokens: list[str] = []
    for match in re.finditer(r"\d{4}-\d{2}-\d{2}|오늘|내일|모레", normalized):
        tokens.append(_resolve_relative_date_token(match.group(0)))
    return tokens


def _extract_time_tokens(text: str) -> list[str]:
    normalized = text.replace(" ", "")
    tokens: list[str] = []

    for match in re.finditer(r"(오전|오후)?(\d{1,2})시", normalized):
        meridiem, hour = match.groups()
        hour_int = int(hour)
        if meridiem == "오후" and hour_int < 12:
            hour_int += 12
        if meridiem == "오전" and hour_int == 12:
            hour_int = 0
        tokens.append(f"{hour_int:02d}:00")

    for match in re.finditer(r"(\d{1,2}):(\d{2})", normalized):
        hour, minute = match.groups()
        tokens.append(f"{int(hour):02d}:{int(minute):02d}")

    deduped: list[str] = []
    for token in tokens:
        if token not in deduped:
            deduped.append(token)
    return deduped


_NAME_BLACKLIST = {"예약", "취소", "변경", "결제", "문의", "입금", "확인", "방문", "시술", "문의요", "취소요", "변경요"}


def _extract_name_hint(text: str) -> str | None:
    clean = text.strip()
    if re.match(r"^[가-힣]{2,4}$", clean) and clean not in _NAME_BLACKLIST:
        return clean

    patterns = (
        r"(?:성함|이름|예약자)\s*[:：]?\s*([가-힣]{2,4})",
        r"^([가-힣]{2,4})\s+(?:\d{4}-\d{2}-\d{2}|01\d-\d{3,4}-\d{4})",
        r"^([가-힣]{2,4})\s+.*?(?:예약|입금|취소|변경)",
        r"([가-힣]{2,4})님",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            candidate = match.group(1).strip()
            if candidate not in _NAME_BLACKLIST:
                return candidate
    return None


def _extract_phone_hint(text: str) -> str | None:
    match = re.search(r"(01[016789]-?\d{3,4}-?\d{4})", text)
    if not match:
        return None
    digits = re.sub(r"\D", "", match.group(1))
    if len(digits) == 11 and digits.startswith("010"):
        return f"{digits[:3]}-{digits[3:7]}-{digits[7:]}"
    return match.group(1)


def _extract_service_display_from_text(text: str) -> str | None:
    normalized = text.replace(" ", "")
    service_map = (
        ("페디큐어", "페디큐어"),
        ("페디", "페디큐어"),
        ("젤네일", "젤네일"),
        ("기본네일", "기본네일"),
        ("기본케어", "기본네일"),
        ("손톱케어", "기본네일"),
    )
    for keyword, display_name in service_map:
        if keyword.replace(" ", "") in normalized:
            return display_name
    return None


def _build_change_followup() -> str:
    return "\n".join(
        [
            CHANGE_MESSAGE.strip(),
            "현재 예약과 새 희망 일정이 모두 확인되어야 변경 처리가 가능합니다.",
            "기존 예약 날짜/시간과 새 희망 날짜/시간을 함께 알려주세요.",
        ]
    )


def _build_cancel_followup() -> str:
    return "\n".join(
        [
            CANCEL_MESSAGE.strip(),
            "취소 대상 예약을 정확히 찾을 수 있도록 예약 날짜/시간을 함께 알려주세요.",
        ]
    )


def _build_payment_followup() -> str:
    return "\n".join(
        [
            PAYMENT_MESSAGE.strip(),
            "입금 확인을 위해 예약자 성함, 예약 날짜, 그리고 가능하다면 결제 키나 거래내역 정보를 함께 알려주세요.",
        ]
    )


def _unique_or_none(items: list[dict]) -> dict | None:
    if len(items) == 1:
        return items[0]
    return None


def _resolve_customer_context(state: ReservationState) -> dict:
    kakao_user_id = state.get("kakao_user_id")
    plusfriend_user_key = state.get("plusfriend_user_key")
    if not kakao_user_id:
        return {}

    lookup = backend_client.lookup_kakao_customer(kakao_user_id, plusfriend_user_key)
    return lookup if lookup.get("success") else {}


def _enrich_slots_with_customer(slots, state: ReservationState):
    lookup = _resolve_customer_context(state)
    if not lookup.get("is_existing"):
        return slots, lookup

    if not slots:
        slots = BookingSlots()

    updates = {}
    if not getattr(slots, "name", None) and lookup.get("name"):
        updates["name"] = lookup.get("name")
    if not getattr(slots, "phone_num", None) and lookup.get("phone_num"):
        updates["phone_num"] = lookup.get("phone_num")

    if not updates:
        return slots, lookup

    if hasattr(slots, "model_copy"):
        return slots.model_copy(update=updates), lookup
    return BookingSlots(**{**slots.dict(), **updates}), lookup


def intake_node(state: ReservationState):
    print("--- [NODE] Intake Agent ---")
    user_input = state["user_input"].strip()

    if not user_input:
        return {
            "intent": "greeting",
            "slots": state.get("slots"),
            "missing_fields": [],
            "is_bookable": False,
            "booking_status": "N/A",
            "next_action": "respond_only",
            "response_draft": WELCOME_MESSAGE,
        }

    result = intake_agent.run(user_input)
    current_intent = _intent_to_str(result.intent)
    intent = _resolve_intent_with_pending(state, current_intent)

    existing_slots = state.get("slots")
    # New explicit booking request after a previous booking is pending payment
    # → discard old slots and booking_id to avoid re-submitting stale data
    is_fresh_booking = (
        current_intent == "booking"
        and not _should_inherit_pending_intent(state, current_intent)
        and state.get("booking_status") == "pending_payment"
    )
    if is_fresh_booking:
        existing_slots = None
    merged_slots = merge_slots(existing_slots, result.slots)
    merged_slots, _customer_lookup = _enrich_slots_with_customer(merged_slots, state)

    # pending이 change/cancel이고 이름이 누락된 상태에서 순수 한국어 이름 입력 시 name 주입
    pending_missing = state.get("pending_missing_fields", [])
    if (
        intent in ("change", "cancel")
        and "name" in pending_missing
        and (merged_slots is None or not merged_slots.name)
        and re.match(r"^[가-힣]{2,4}$", user_input.strip())
        and user_input.strip() not in _NAME_BLACKLIST
    ):
        name_hint = user_input.strip()
        if merged_slots is None:
            merged_slots = BookingSlots(name=name_hint)
        elif hasattr(merged_slots, "model_copy"):
            merged_slots = merged_slots.model_copy(update={"name": name_hint})
        else:
            merged_slots = BookingSlots(**{**merged_slots.dict(), "name": name_hint})

    required_fields = ["name", "phone_num", "off_removal", "reserve_date", "reserve_time", "service_code", "past_visit"]
    missing_fields = [field for field in required_fields if getattr(merged_slots, field, None) is None]
    missing_count = len(missing_fields)

    if intent != "booking":
        # 취소/변경 확인 대기 중이면 next_action과 pending 상태를 보존
        if intent in ("cancel", "change") and state.get("next_action") == "await_cancel_confirmation":
            return {
                "intent": intent,
                "slots": merged_slots,
                "missing_fields": [],
                "is_bookable": False,
                "booking_status": "N/A",
                "next_action": "await_cancel_confirmation",
                "response_draft": "",
            }
        return {
            "intent": intent,
            "slots": merged_slots,
            "missing_fields": [],
            "is_bookable": False,
            "booking_status": "N/A",
            "next_action": "respond_only",
            "response_draft": "",
            **_clear_pending_state(),
        }

    fresh_booking_reset = {"booking_id": None} if is_fresh_booking else {}

    if missing_count >= 3:
        shop_info = backend_client.get_shop_info()
        booking_form_text = _resolve_shop_text(shop_info, "booking_form_text", BOOKING_FORM_GUIDE)
        return {
            "intent": "booking",
            "slots": merged_slots,
            "missing_fields": missing_fields,
            "is_bookable": False,
            "booking_status": "N/A",
            "next_action": "ask_followup",
            "response_draft": booking_form_text,
            **_pending_state_update("booking", missing_fields, booking_form_text),
            **fresh_booking_reset,
        }

    response_draft = _build_followup_question(missing_fields) if missing_count > 0 else ""
    return {
        "intent": "booking",
        "slots": merged_slots,
        "missing_fields": missing_fields,
        "is_bookable": False,
        "booking_status": "N/A",
        "next_action": "ask_followup" if missing_count > 0 else "validate_booking",
        "response_draft": response_draft,
        **(_pending_state_update("booking", missing_fields, response_draft) if missing_count > 0 else _clear_pending_state()),
        **fresh_booking_reset,
    }


def booking_node(state: ReservationState):
    print("--- [NODE] Booking Logic (Backend Integration) ---")

    intent = _intent_to_str(state.get("intent", ""))
    if intent != "booking":
        return {
            "is_bookable": False,
            "booking_status": "N/A",
            "next_action": "respond_only",
            "response_draft": state.get("response_draft") or build_non_booking_response(intent),
        }

    slots = state.get("slots")
    slots, _customer_lookup = _enrich_slots_with_customer(slots, state)

    if not slots or not slots.reserve_date or not slots.reserve_time:
        draft = state.get("response_draft") or BOOKING_MISSING_DATETIME_MESSAGE
        return {
            "is_bookable": False,
            "booking_status": "N/A",
            "next_action": "ask_followup",
            "response_draft": draft,
            **_pending_state_update("booking", ["reserve_date", "reserve_time"], draft),
        }

    shop_info = backend_client.get_shop_info()
    if not shop_info.get("success", True):
        return {
            "is_bookable": False,
            "booking_status": "backend_error",
            "next_action": shop_info.get("next_action", "human_review"),
            "response_draft": "현재 샵 설정 정보를 불러올 수 없어 예약 진행이 어렵습니다. 확인 후 안내드릴게요.",
            **_clear_pending_state(),
            "policy_check_results": {
                "source": shop_info.get("source"),
                "status_code": shop_info.get("status_code"),
                "error_code": shop_info.get("error_code"),
                "message": shop_info.get("message"),
            },
        }

    schedule = backend_client.get_schedule(slots.reserve_date)
    if not schedule.get("success", True):
        return {
            "is_bookable": False,
            "booking_status": "backend_error",
            "next_action": "retry_or_human_review",
            "response_draft": "현재 예약 시스템 연결이 원활하지 않아 예약 가능 시간을 확인하기 어렵습니다. 확인 후 안내드릴게요.",
            **_clear_pending_state(),
            "policy_check_results": {
                "source": schedule.get("source"),
                "business_hours": schedule.get("business_hours"),
                "booked_slots": schedule.get("booked_slots"),
            },
        }

    duration = PolicyEngine.calculate_duration(
        slots.service_code,
        slots.off_removal,
        service_durations=shop_info.get("service_durations"),
    )

    check = PolicyEngine.validate_reservation(
        slots.reserve_date,
        slots.reserve_time,
        duration,
        schedule["booked_slots"],
        business_hours=schedule["business_hours"],
        closed_days=shop_info.get("closed_days"),
    )

    if check["valid"]:
        reservation_payload = backend_client.build_reservation_payload(
            slots,
            duration,
            deposit_amount=shop_info["deposit_amount"],
            designer=state.get("designer"),
            kakao_user_id=state.get("kakao_user_id"),
            plusfriend_user_key=state.get("plusfriend_user_key"),
        )
        reservation_result = backend_client.create_reservation(reservation_payload)
        reserve_time_range = reservation_payload["reserve_time"]

        reserve_date = reservation_payload["reserve_date"]
        response_parts = [
            "예약 정보가 임시 저장되었습니다.",
            "입금 안내를 확인해 주세요.",
            f"- 예약 날짜: {reserve_date}",
            f"- 예약 시간: {reserve_time_range}",
            f"- 예상 소요 시간: 약 {duration}분",
            f"- 예약금: {shop_info['deposit_amount']}원",
        ]

        resp_data = reservation_result.get("response") or {}
        if isinstance(resp_data.get("data"), dict):
            booking_id = resp_data["data"].get("id")
        else:
            booking_id = resp_data.get("id")

        if not booking_id and slots.name and slots.reserve_date:
            candidates = backend_client.find_reservations(name=slots.name, reserve_date=slots.reserve_date)
            if candidates:
                booking_id = candidates[-1].get("id")

        if booking_id:
            backend_url = os.getenv("BACKEND_BASE_URL", "http://localhost:8000").rstrip("/")
            service_name = _get_service_display_name(slots.service_code or "")
            params = urlencode({
                "orderId": f"booking_{booking_id}",
                "amount": shop_info["deposit_amount"],
                "orderName": f"{service_name} 예약금",
                "customerName": slots.name or "",
            })
            payment_url = f"{backend_url}/payment?{params}"
            response_parts.append(
                f"\n💳 예약금 결제 링크:\n{payment_url}"
                f"\n\n결제 완료 후 '결제 완료'라고 보내주시면 확인해드리겠습니다 😊"
            )

        response = "\n".join(part for part in response_parts if part)
        return {
            "is_bookable": True,
            "booking_status": "pending_payment",
            "booking_id": booking_id,
            "response_draft": response,
            "next_action": "notify_success",
            **_clear_pending_state(),
            "policy_check_results": {
                "source": schedule["source"],
                "business_hours": schedule["business_hours"],
                "booked_slots": schedule["booked_slots"],
                "deposit_amount": shop_info["deposit_amount"],
                "reservation_result": reservation_result,
            },
        }

    weekday_label = _weekday_korean(slots.reserve_date)
    weekday_text = f" ({weekday_label})" if weekday_label else ""
    is_closed_day = "휴무" in check["reason"]

    if is_closed_day:
        rec_block = "다른 날짜로 예약 형식을 다시 작성해서 보내주시면 확인해드리겠습니다 😊"
    else:
        recommendations = PolicyEngine.get_available_recommendations(schedule["business_hours"], schedule["booked_slots"], duration)
        if recommendations:
            rec_text = "\n".join(f"• {item}" for item in recommendations)
            rec_block = f"대신 현재 예약 가능한 시간대는 다음과 같습니다.\n{rec_text}"
        else:
            rec_block = "현재 예약 가능한 시간대를 찾지 못했습니다.\n다른 날짜를 알려주시면 다시 확인해드릴게요."

    response = f"죄송합니다 고객님, {check['reason']}\n예약 요청 날짜: {slots.reserve_date}{weekday_text}\n\n{rec_block}"
    return {
        "is_bookable": False,
        "booking_status": "rejected",
        "response_draft": response,
        "next_action": "notify_failure",
        **_pending_state_update("booking", ["reserve_time"], response),
        "policy_check_results": {
            "source": schedule["source"],
            "business_hours": schedule["business_hours"],
            "booked_slots": schedule["booked_slots"],
            "reason": check["reason"],
        },
    }


def change_node(state: ReservationState):
    print("--- [NODE] Change Node ---")

    intent = _intent_to_str(state.get("intent", ""))
    if intent != "change":
        return {
            "booking_status": "N/A",
            "next_action": "respond_only",
            "response_draft": build_non_booking_response(intent),
        }

    user_input = state.get("user_input", "")
    slots = state.get("slots")
    slots, _customer_lookup = _enrich_slots_with_customer(slots, state)
    name = (slots.name if slots else None) or _extract_name_hint(user_input)

    if not name:
        followup = "예약 변경을 도와드리겠습니다. 예약하실 때 사용하신 성함을 알려주세요."
        return {
            "booking_status": "N/A",
            "next_action": "ask_followup",
            "response_draft": followup,
            **_pending_state_update("change", ["name"], followup),
        }

    phone_num = (slots.phone_num if slots else None) or _extract_phone_hint(user_input)
    date_tokens = _extract_date_tokens(user_input)
    time_tokens = _extract_time_tokens(user_input)
    service = _get_service_display_name(slots.service_code) if slots and slots.service_code else _extract_service_display_from_text(user_input)

    # 이전 턴에서 이미 찾은 예약이 있으면 재검색 없이 재사용
    # (intake_node가 booking_status를 N/A로 덮어쓰므로 booking_status로 판단 불가)
    prev_matched = (state.get("policy_check_results") or {}).get("matched_reservation")
    if prev_matched:
        matched = prev_matched
    else:
        reserve_date = date_tokens[0] if date_tokens else None
        reserve_time = time_tokens[0] if time_tokens else None
        candidates = backend_client.find_reservations(name=name, phone_num=phone_num, reserve_date=reserve_date, reserve_time=reserve_time, service=service)
        matched = _unique_or_none(candidates)

        if matched is None:
            if not candidates:
                nearest = _pick_nearest_future(backend_client.find_reservations(name=name))
                if nearest:
                    matched = nearest
                else:
                    followup = f"'{name}'님 명의의 예약을 찾을 수 없어요.\n변경할 예약의 날짜와 시간을 알려주시겠어요?\n예) 2026-06-15 14:00"
                    return {
                        "booking_status": "N/A",
                        "next_action": "ask_followup",
                        "response_draft": followup,
                        **_pending_state_update("change", ["reserve_date", "reserve_time"], followup),
                        "policy_check_results": {"matched_reservations": []},
                    }

            if matched is None:
                followup = "\n".join([
                    "여러 예약이 검색되었습니다.",
                    _candidate_summary_lines(candidates),
                    "변경할 예약의 날짜와 시간을 알려주세요.",
                ])
                return {
                    "booking_status": "N/A",
                    "next_action": "ask_followup",
                    "response_draft": followup,
                    **_pending_state_update("change", ["reserve_date", "reserve_time"], followup),
                    "policy_check_results": {"matched_reservations": candidates},
                }

    # prev_matched 있으면 현재 입력 1개를 new로, 없으면 마지막 2개 중 new
    if prev_matched and date_tokens and time_tokens:
        new_reserve_date = date_tokens[0]
        new_reserve_time = time_tokens[0]
    elif len(date_tokens) >= 2 and len(time_tokens) >= 2:
        new_reserve_date = date_tokens[-1]
        new_reserve_time = time_tokens[-1]
    else:
        followup = "\n".join([
            f"{matched.get('name')}님의 예약을 찾았습니다.",
            f"📅 {matched.get('reserve_date')} {matched.get('reserve_time')} {matched.get('service', '')}",
            "",
            "변경 희망 날짜와 시간을 알려주시면 바로 반영하겠습니다.",
            "예) 2026-06-20 15:00",
        ])
        return {
            "booking_status": "pending_review",
            "next_action": "ask_followup",
            "response_draft": followup,
            **_pending_state_update("change", ["reserve_date", "reserve_time"], followup),
            "policy_check_results": {"matched_reservation": matched},
        }
    if not new_reserve_date or not new_reserve_time:
        followup = "\n".join(
            [
                f"{matched.get('name')}님의 예약을 찾았습니다.",
                f"📅 {matched.get('reserve_date')} {matched.get('reserve_time')} {matched.get('service', '')}",
                "",
                "변경 희망 날짜와 시간을 알려주시면 바로 반영하겠습니다.",
                "예) 2026-06-20 15:00",
            ]
        )
        return {
            "booking_status": "pending_review",
            "next_action": "ask_followup",
            "response_draft": followup,
            **_pending_state_update("change", ["reserve_date", "reserve_time"], followup),
            "policy_check_results": {"matched_reservation": matched},
        }

    service_code = _service_code_from_display_name(matched.get("service"))
    off_removal = bool(matched.get("off_removal"))
    duration_min = PolicyEngine.calculate_duration(service_code or "GEL_NAIL", off_removal)

    schedule = backend_client.get_schedule(new_reserve_date)
    if not schedule.get("success", True):
        return {
            "booking_status": "backend_error",
            "next_action": "retry_or_human_review",
            "response_draft": "새 희망 날짜의 예약 가능 시간을 확인할 수 없어 변경 처리를 잠시 보류했어요. 잠시 후 다시 시도해주세요.",
            **_clear_pending_state(),
            "policy_check_results": {
                "matched_reservation": matched,
                "schedule_error": schedule,
            },
        }

    matched_reserve_time = str(matched.get("reserve_time", ""))
    booked_slots = [slot for slot in schedule["booked_slots"] if str(slot.get("reserve_time", "")) != matched_reserve_time]

    validation = PolicyEngine.validate_reservation(
        new_reserve_date,
        new_reserve_time,
        duration_min,
        booked_slots,
        business_hours=schedule["business_hours"],
    )
    if not validation["valid"]:
        recommendations = PolicyEngine.get_available_recommendations(schedule["business_hours"], booked_slots, duration_min)
        rec_text = " / ".join(recommendations) if recommendations else "추천 가능한 시간대를 찾지 못했습니다."
        return {
            "booking_status": "rejected",
            "next_action": "ask_followup",
            "response_draft": "\n".join(
                [
                    f"죄송합니다. {validation['reason']}",
                    "",
                    f"대신 가능한 시간대는 다음과 같습니다.",
                    rec_text,
                    "",
                    "원하시는 시간을 말씀해 주시면 변경해드리겠습니다 😊",
                ]
            ),
            **_pending_state_update("change", ["reserve_date", "reserve_time"], ""),
            "policy_check_results": {
                "matched_reservation": matched,
                "business_hours": schedule["business_hours"],
                "booked_slots": booked_slots,
                "reason": validation["reason"],
            },
        }

    new_reserve_time_range = f"{new_reserve_time}-{(datetime.strptime(new_reserve_time, '%H:%M') + timedelta(minutes=duration_min)).strftime('%H:%M')}"
    payload = {
        "reserve_date": new_reserve_date,
        "reserve_time": new_reserve_time_range,
        "estimated_duration_min": duration_min,
    }
    update_result = backend_client.update_reservation(int(matched["id"]), payload)
    if not update_result.get("success", True):
        return {
            "booking_status": "backend_error",
            "next_action": update_result.get("next_action", "human_review"),
            "response_draft": "예약 변경 처리 중 오류가 발생했어요. 잠시 후 다시 시도하거나 사장님 확인이 필요합니다.",
            **_clear_pending_state(),
            "policy_check_results": {
                "matched_reservation": matched,
                "update_result": update_result,
            },
        }

    response = "\n".join(
        [
            "✅ 예약이 변경되었습니다!",
            "",
            f"📅 변경된 일정: {new_reserve_date} {new_reserve_time_range}",
            "",
            "또 궁금하신 점이 있으면 편하게 말씀해 주세요 😊",
        ]
    )
    return {
        "booking_status": "updated",
        "next_action": "notify_success",
        "response_draft": response,
        **_clear_pending_state(),
        "policy_check_results": {
            "matched_reservation": matched,
            "update_result": update_result,
            "business_hours": schedule["business_hours"],
            "booked_slots": booked_slots,
        },
    }


def cancel_node(state: ReservationState):
    print("--- [NODE] Cancel Node ---")

    intent = _intent_to_str(state.get("intent", ""))
    if intent != "cancel":
        return {
            "booking_status": "N/A",
            "next_action": "respond_only",
            "response_draft": build_non_booking_response(intent),
        }

    user_input = state.get("user_input", "").strip()

    # 확인 대기 상태: 고객의 맞아요/아니요 처리
    if state.get("next_action") == "await_cancel_confirmation":
        matched = (state.get("policy_check_results") or {}).get("matched_reservation")
        if matched:
            if _is_affirmative(user_input):
                reservation_id = int(matched["id"])
                is_paid = str(matched.get("payment_status", "")).upper() == "PAID"

                if is_paid:
                    refund_result = backend_client.refund_payment(reservation_id)
                    if not refund_result.get("success", True):
                        return {
                            "booking_status": "backend_error",
                            "next_action": "human_review",
                            "response_draft": "환불 처리 중 오류가 발생했어요. 잠시 후 다시 시도하거나 사장님 확인이 필요합니다.",
                            **_clear_pending_state(),
                        }
                    cancel_result = refund_result
                else:
                    cancel_result = backend_client.delete_reservation(reservation_id)
                    if not cancel_result.get("success", True):
                        return {
                            "booking_status": "backend_error",
                            "next_action": cancel_result.get("next_action", "human_review"),
                            "response_draft": "예약 취소 처리 중 오류가 발생했어요. 잠시 후 다시 시도하거나 사장님 확인이 필요합니다.",
                            **_clear_pending_state(),
                        }
                response = "\n".join([
                    f"{matched.get('name')}님의 예약이 취소되었습니다. 😢",
                    "",
                    "취소된 예약:",
                    f"📅 {matched.get('reserve_date')} {matched.get('reserve_time')}",
                    f"💅 {matched.get('service', '')}",
                    *([" ", "💸 예약금은 3~5일 내 환불됩니다. (결제사에 따라 상이)"] if is_paid else []),
                    "",
                    "또 방문해 주세요!",
                ])
                return {
                    "booking_status": "cancelled",
                    "next_action": "notify_success",
                    "response_draft": response,
                    **_clear_pending_state(),
                    "policy_check_results": {"matched_reservation": matched, "cancel_result": cancel_result},
                }
            if _is_negative(user_input):
                followup = "취소할 예약의 날짜와 시간을 알려주시겠어요?\n예) 2026-06-15 14:00"
                return {
                    "booking_status": "N/A",
                    "next_action": "ask_followup",
                    "response_draft": followup,
                    **_pending_state_update("cancel", ["reserve_date", "reserve_time"], followup),
                }
        # 명확하지 않은 답변 → 재질문
        confirmation_msg = _build_cancel_confirmation_message(matched) if matched else "취소 여부를 맞아요 또는 아니요로 알려주세요."
        return {
            "booking_status": "N/A",
            "next_action": "await_cancel_confirmation",
            "response_draft": confirmation_msg,
            **_pending_state_update("cancel", [], confirmation_msg),
            "policy_check_results": {"matched_reservation": matched},
        }

    slots = state.get("slots")
    slots, _customer_lookup = _enrich_slots_with_customer(slots, state)
    name = (slots.name if slots else None) or _extract_name_hint(user_input)

    if not name:
        followup = "예약 취소를 도와드리겠습니다. 예약하실 때 사용하신 성함을 알려주세요."
        return {
            "booking_status": "N/A",
            "next_action": "ask_followup",
            "response_draft": followup,
            **_pending_state_update("cancel", ["name"], followup),
        }

    phone_num = (slots.phone_num if slots else None) or _extract_phone_hint(user_input)
    slot_date = (slots.reserve_date if slots else None)
    slot_time = (slots.reserve_time if slots else None)
    date_tokens = _extract_date_tokens(user_input)
    time_tokens = _extract_time_tokens(user_input)
    reserve_date = slot_date or (date_tokens[0] if date_tokens else None)
    reserve_time = slot_time or (time_tokens[0] if time_tokens else None)

    # 슬롯에 날짜/시간이 있으면 그것으로 먼저 검색, 없으면 이름으로 전체 검색 후 nearest 선택
    if reserve_date or reserve_time:
        candidates = backend_client.find_reservations(name=name, phone_num=phone_num, reserve_date=reserve_date, reserve_time=reserve_time)
    else:
        all_candidates = backend_client.find_reservations(name=name)
        nearest = _pick_nearest_future(all_candidates)
        if nearest:
            confirmation_msg = _build_cancel_confirmation_message(nearest)
            return {
                "booking_status": "N/A",
                "next_action": "await_cancel_confirmation",
                "response_draft": confirmation_msg,
                **_pending_state_update("cancel", [], confirmation_msg),
                "policy_check_results": {"matched_reservation": nearest},
            }
        candidates = all_candidates

    matched = _unique_or_none(candidates)

    if matched is None:
        if not candidates:
            followup = f"'{name}'님 명의의 예약을 찾을 수 없어요.\n취소할 예약의 날짜와 시간을 알려주시겠어요?\n예) 2026-06-15 14:00"
            return {
                "booking_status": "N/A",
                "next_action": "ask_followup",
                "response_draft": followup,
                **_pending_state_update("cancel", ["reserve_date", "reserve_time"], followup),
                "policy_check_results": {"matched_reservations": []},
            }
        followup = "\n".join([
            "여러 예약이 검색되었습니다.",
            _candidate_summary_lines(candidates),
            "취소할 예약의 날짜와 시간을 알려주세요.",
        ])
        return {
            "booking_status": "N/A",
            "next_action": "ask_followup",
            "response_draft": followup,
            **_pending_state_update("cancel", ["reserve_date", "reserve_time"], followup),
            "policy_check_results": {"matched_reservations": candidates},
        }

    confirmation_msg = _build_cancel_confirmation_message(matched)
    return {
        "booking_status": "N/A",
        "next_action": "await_cancel_confirmation",
        "response_draft": confirmation_msg,
        **_pending_state_update("cancel", [], confirmation_msg),
        "policy_check_results": {"matched_reservation": matched},
    }


def payment_node(state: ReservationState):
    print("--- [NODE] Payment Node ---")

    intent = _intent_to_str(state.get("intent", ""))
    if intent != "payment":
        return {
            "booking_status": "N/A",
            "next_action": "respond_only",
            "response_draft": build_non_booking_response(intent),
        }

    user_input = state.get("user_input", "")
    slots = state.get("slots")
    slots, customer_lookup = _enrich_slots_with_customer(slots, state)
    name = (slots.name if slots else None) or customer_lookup.get("name") or _extract_name_hint(user_input)

    if not name:
        followup = "결제 확인을 위해 예약하실 때 사용하신 성함을 알려주세요."
        return {
            "booking_status": "N/A",
            "next_action": "ask_followup",
            "response_draft": followup,
            **_pending_state_update("payment", ["name"], followup),
        }

    import base64
    import httpx

    booking_id = state.get("booking_id")
    is_paid = False

    toss_secret = os.getenv("TOSS_SECRET_KEY", "")
    if booking_id and toss_secret:
        order_id = f"booking_{booking_id}"
        encoded = base64.b64encode(f"{toss_secret}:".encode()).decode()
        try:
            resp = httpx.get(
                f"https://api.tosspayments.com/v1/payments/orders/{order_id}",
                headers={"Authorization": f"Basic {encoded}"},
                timeout=5,
            )
            if resp.status_code == 200:
                is_paid = resp.json().get("status") == "DONE"
        except Exception:
            pass

    if not is_paid:
        # Toss API 조회 실패 또는 미결제 시 백엔드로 fallback
        snapshot = backend_client.list_reservations()
        bookings = snapshot.get("bookings", [])
        my_bookings = [b for b in bookings if b.get("name") == name]
        my_bookings.sort(key=lambda item: item.get("reserve_date", ""), reverse=True)
        my_booking = my_bookings[0] if my_bookings else None
        is_paid = bool(my_booking and my_booking.get("payment_status") == "PAID")

    if is_paid:
        return {
            "booking_status": "payment_confirmed",
            "next_action": "notify_success",
            "response_draft": "✅ 결제가 확인되었습니다!\n예약이 완료되었어요 :)",
            **_clear_pending_state(),
        }
    return {
        "booking_status": "pending_payment",
        "next_action": "notify_failure",
        "response_draft": "⚠️ 아직 결제가 확인되지 않았습니다.\n잠시 후 다시 시도해주세요.",
        **_clear_pending_state(),
    }


def inquiry_node(state: ReservationState):
    print("--- [NODE] Inquiry Agent ---")
    user_input = state.get("user_input", "").strip()
    shop_info = backend_client.get_shop_info()
    result = inquiry_agent.run(user_input, shop_info)

    if result.is_trigger:
        followup = "궁금하신 점을 남겨주세요!\n가격, 영업시간, 예약 정책 등 무엇이든 편하게 문의해 주세요😊"
        return {
            "booking_status": "N/A",
            "next_action": "ask_followup",
            "response_draft": followup,
            **_pending_state_update("inquiry", [], followup),
        }

    if result.answered:
        return {
            "booking_status": "N/A",
            "next_action": "respond_only",
            "response_draft": result.answer,
            **_clear_pending_state(),
        }

    slots = state.get("slots")
    customer_name = getattr(slots, "name", None) or "고객"
    backend_client.notify_owner(customer_name=customer_name, waiting=True)
    return {
        "booking_status": "N/A",
        "next_action": "respond_only",
        "response_draft": INQUIRY_FALLBACK_MESSAGE,
        **_clear_pending_state(),
    }


def response_node(state: ReservationState):
    print("--- [NODE] Response Draft ---")

    draft = state.get("response_draft")
    if not draft:
        intent = _intent_to_str(state.get("intent", "unknown"))
        if intent == "booking":
            shop_info = backend_client.get_shop_info()
            draft = _resolve_shop_text(shop_info, "booking_form_text", BOOKING_FORM_GUIDE)
        else:
            draft = build_non_booking_response(intent)

    draft = draft.strip()

    booking_status = state.get("booking_status", "")
    current_intent = _intent_to_str(state.get("intent", ""))
    if booking_status == "pending_payment" and "💳" not in draft and current_intent != "payment":
        draft += "\n\n예약금 결제 링크는 잠시 후 별도로 안내드리겠습니다."

    intent = _intent_to_str(state.get("intent", ""))
    if intent == "unknown":
        slots = state.get("slots")
        customer_name = getattr(slots, "name", None) or "고객"
        backend_client.notify_owner(customer_name=customer_name, waiting=True)

    return {"response_draft": draft}
