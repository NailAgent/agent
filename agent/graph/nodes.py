import re
from datetime import datetime, timedelta

from agent.graph.state import ReservationState, merge_slots
from agent.agents.intake_agent import IntakeAgent
from agent.agents.schema import BookingSlots
from agent.tools.backend_client import BackendClient
from agent.tools.policy_engine import PolicyEngine
from agent.agents.constants import (
    BOOKING_FORM_GUIDE,
    CANCEL_MESSAGE,
    CHANGE_MESSAGE,
    INQUIRY_FALLBACK_MESSAGE,
    BOOKING_MISSING_DATETIME_MESSAGE,
    PAYMENT_MESSAGE,
    UNKNOWN_FALLBACK_MESSAGE,
    WELCOME_MESSAGE,
)

# Intake Agent Instance
intake_agent = IntakeAgent()
backend_client = BackendClient()

# ── 공통 유틸 ────────────────────────────────────────────────────────────────

def _intent_to_str(intent) -> str:
    """Enum 또는 문자열 intent를 plain string으로 정규화."""
    return intent.value if hasattr(intent, "value") else str(intent or "")

def build_non_booking_response(intent: str) -> str:
    """예약 외 intent에 대한 v1 고정 응답 반환."""

    # v1: Only the booking flow has a dedicated node in v1.
    # v2: Route change/cancel/payment to dedicated nodes instead of returning fallback messages.
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


def _extract_backend_status(reservation_result: dict) -> str:
    """백엔드 응답에서 HTTP 상태 코드 문자열 추출."""
    response = reservation_result.get("response") or {}
    status = response.get("status") or reservation_result.get("status_code")
    if status:
        return f"HTTP {status}"
    return "HTTP 상태 미상"


def _resolve_shop_text(shop_info: dict, key: str, fallback: str) -> str:
    """shop_info에서 특정 텍스트 키를 읽되, 없으면 fallback 반환."""
    value = shop_info.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


# ── 날짜/시간 파싱 ────────────────────────────────────────────────────────────

_RELATIVE_DATE_OFFSETS = {
    "오늘": 0,
    "내일": 1,
    "모레": 2,
}


def _service_code_from_display_name(service_name: str | None) -> str | None:
    """한국어 서비스명을 서비스 코드로 역변환."""
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
    """오늘/내일/모레를 YYYY-MM-DD 절대 날짜로 변환."""
    if token in _RELATIVE_DATE_OFFSETS:
        return (datetime.now().date() + timedelta(days=_RELATIVE_DATE_OFFSETS[token])).strftime("%Y-%m-%d")
    return token


def _extract_date_tokens(text: str) -> list[str]:
    """텍스트에서 날짜 토큰을 추출해 절대 날짜(YYYY-MM-DD) 리스트로 반환."""
    normalized = text.replace(" ", "")
    tokens: list[str] = []
    for match in re.finditer(r"\d{4}-\d{2}-\d{2}|오늘|내일|모레", normalized):
        tokens.append(_resolve_relative_date_token(match.group(0)))
    return tokens


def _extract_time_tokens(text: str) -> list[str]:
    """텍스트에서 시간 토큰을 추출해 HH:MM 형식 리스트로 반환."""
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


# ── 결제/환불 파싱 ────────────────────────────────────────────────────────────

def _extract_payment_key(text: str) -> str | None:
    """텍스트에서 결제 키 추출."""
    pattern = r"(?:payment[_\- ]?key|결제키|paymentkey)\s*[:=]?\s*([A-Za-z0-9_-]{6,})"
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def _is_refund_request(text: str) -> bool:
    """환불 요청 여부 판별."""
    normalized = text.replace(" ", "")
    return any(keyword in normalized for keyword in ("환불", "환급", "취소환불"))


def _extract_amount_from_text(text: str) -> int | None:
    """텍스트에서 금액(원) 추출."""
    match = re.search(r"(\d[\d,]*)\s*원", text)
    if not match:
        return None
    return int(match.group(1).replace(",", ""))


# ── 고객 정보 파싱 ────────────────────────────────────────────────────────────

def _extract_name_hint(text: str) -> str | None:
    """텍스트에서 예약자 이름 힌트 추출."""
    patterns = (
        r"(?:성함|이름|예약자)\s*[:：]?\s*([가-힣]{2,4})",
        r"^([가-힣]{2,4})\s+(?:\d{4}-\d{2}-\d{2}|01\d-\d{3,4}-\d{4})",
        r"^([가-힣]{2,4})\s+.*?(?:예약|입금|취소|변경)",
        r"([가-힣]{2,4})님",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()
    return None


def _extract_phone_hint(text: str) -> str | None:
    """텍스트에서 전화번호 힌트 추출."""
    match = re.search(r"(01[016789]-?\d{3,4}-?\d{4})", text)
    if not match:
        return None
    digits = re.sub(r"\D", "", match.group(1))
    if len(digits) == 11 and digits.startswith("010"):
        return f"{digits[:3]}-{digits[3:7]}-{digits[7:]}"
    return match.group(1)


def _extract_service_display_from_text(text: str) -> str | None:
    """텍스트에서 서비스 한국어명 추출."""
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


# ── Followup 메시지 빌더 ──────────────────────────────────────────────────────

def _build_change_followup() -> str:
    """예약 변경 followup 안내 메시지 생성."""
    return (
        f"{CHANGE_MESSAGE.strip()}\n"
        "현재 예약과 새 희망 일정이 모두 확인되어야 변경 처리가 가능합니다.\n"
        "기존 예약 날짜/시간과 새 희망 날짜/시간을 함께 알려주세요."
    )


def _build_cancel_followup() -> str:
    """예약 취소 followup 안내 메시지 생성."""
    return (
        f"{CANCEL_MESSAGE.strip()}\n"
        "취소 대상 예약을 정확히 찾을 수 있도록 예약 날짜/시간을 함께 알려주세요."
    )


def _build_payment_followup() -> str:
    """입금 확인 followup 안내 메시지 생성."""
    return (
        f"{PAYMENT_MESSAGE.strip()}\n"
        "입금 확인을 위해 예약자 성함, 예약 날짜, 그리고 가능하다면 결제 키나 거래내역 정보를 함께 알려주세요."
    )


# ── 고객 조회 ─────────────────────────────────────────────────────────────────

def _unique_or_none(items: list[dict]) -> dict | None:
    """리스트가 정확히 1건일 때만 반환, 여러 건이면 None."""
    if len(items) == 1:
        return items[0]
    return None


def _resolve_customer_context(state: ReservationState) -> dict:
    """kakao_user_id로 백엔드 기존 고객 조회 (/api/v1/kakao-customers)."""
    kakao_user_id = state.get("kakao_user_id")
    plusfriend_user_key = state.get("plusfriend_user_key")
    if not kakao_user_id:
        return {}

    lookup = backend_client.lookup_kakao_customer(kakao_user_id, plusfriend_user_key)
    return lookup if lookup.get("success") else {}


def _enrich_slots_with_customer(slots, state: ReservationState):
    """기존 고객이면 slots의 이름/전화번호를 자동 보완."""
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


# ── 메인 노드 ─────────────────────────────────────────────────────────────────

def intake_node(state: ReservationState):
    """사용자 발화를 분석해 intent와 슬롯을 추출하고, 멀티턴 슬롯을 병합."""
    print("--- [NODE] Intake Agent ---")
    user_input = state["user_input"].strip()

    # 1. Handle empty input
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

    # 2. Extract from current input
    result = intake_agent.run(user_input)
    intent = _intent_to_str(result.intent)

    # 3. Merge with existing slots (Multi-turn Memory Fix)
    existing_slots = state.get("slots")
    merged_slots = merge_slots(existing_slots, result.slots)
    merged_slots, customer_lookup = _enrich_slots_with_customer(merged_slots, state)

    # 4. Recalculate missing fields based on merged data
    required_fields = ["name", "phone_num", "off_removal", "reserve_date", "reserve_time", "service_code", "past_visit"]
    missing_fields = [f for f in required_fields if getattr(merged_slots, f, None) is None]
    missing_count = len(missing_fields)

    # v1: Only booking intent gets detailed slot handling.
    if intent != "booking":
        return {
            "intent": intent,
            "slots": merged_slots,
            "missing_fields": [],
            "is_bookable": False,
            "booking_status": "N/A",
            "next_action": "respond_only",
            "response_draft": "",
        }

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
            "response_draft": booking_form_text
        }

    # Use the LLM's suggested followup if present, otherwise build one
    response_draft = result.followup_question if (result.need_followup and result.followup_question) else ""

    return {
        "intent": "booking",
        "slots": merged_slots,
        "missing_fields": missing_fields,
        "is_bookable": False,
        "booking_status": "N/A",
        "next_action": "ask_followup" if missing_count > 0 else "validate_booking",
        "response_draft": response_draft
    }


def booking_node(state: ReservationState):
    """예약 가능 여부를 검증하고, 가능하면 백엔드에 예약을 생성."""
    print("--- [NODE] Booking Logic (Backend Integration) ---")

    intent = _intent_to_str(state.get("intent", ""))

    if intent != "booking":
        return {
            "is_bookable": False,
            "booking_status": "N/A",
            "next_action": "respond_only",
            "response_draft": state.get("response_draft") or build_non_booking_response(intent)
        }

    slots = state.get("slots")
    slots, customer_lookup = _enrich_slots_with_customer(slots, state)

    if not slots or not slots.reserve_date or not slots.reserve_time:
        return {
            "is_bookable": False,
            "booking_status": "N/A",
            "next_action": "ask_followup",
            "response_draft": state.get("response_draft")
            or BOOKING_MISSING_DATETIME_MESSAGE,
        }

    shop_info = backend_client.get_shop_info()
    if not shop_info.get("success", True):
        return {
            "is_bookable": False,
            "booking_status": "backend_error",
            "next_action": shop_info.get("next_action", "human_review"),
            "response_draft": "현재 샵 설정 정보를 불러올 수 없어 예약 진행이 어렵습니다. 확인 후 안내드릴게요.",
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
            "policy_check_results": {
                "source": schedule.get("source"),
                "business_hours": schedule.get("business_hours"),
                "booked_slots": schedule.get("booked_slots"),
            },
        }

    # 1. 소요 시간 계산
    duration = PolicyEngine.calculate_duration(slots.service_code, slots.off_removal)

    # 2. 예약 가능 여부 검증 (Policy Engine 호출)
    check = PolicyEngine.validate_reservation(
        slots.reserve_date,
        slots.reserve_time,
        duration,
        schedule["booked_slots"],
        business_hours=schedule["business_hours"],
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
        backend_status = _extract_backend_status(reservation_result)
        base_message = _resolve_shop_text(shop_info, "booking_message_text", "안녕하세요 고객님, 해당 시간 예약이 가능합니다!")
        followup_line = "입금 안내를 도와드릴까요?"
        if "입금 안내" in base_message or "도와드릴까요" in base_message:
            followup_line = ""

        response_parts = [
            base_message,
            f"- 예약 희망 시간: {reserve_time_range}",
            f"- 예상 소요 시간: 약 {duration}분",
            f"- 예약금: {shop_info['deposit_amount']}원",
        ]
        if reservation_result.get("source") == "backend":
            response_parts.append(f"예약이 백엔드에 등록되었습니다. ({backend_status})")
        else:
            response_parts.append("예약 정보가 임시 저장되었습니다.")
        if followup_line:
            response_parts.append(followup_line)
        response = "\n".join(part for part in response_parts if part)
        return {
            "is_bookable": True,
            "booking_status": "pending_payment",
            "response_draft": response,
            "next_action": "notify_success",
            "policy_check_results": {
                "source": schedule["source"],
                "business_hours": schedule["business_hours"],
                "booked_slots": schedule["booked_slots"],
                "deposit_amount": shop_info["deposit_amount"],
                "backend_status": backend_status,
                "reservation_result": reservation_result,
            },
        }
    else:
        # 3. 예약 불가 시 대체 시간 추천 (백엔드 데이터를 기반으로 에이전트가 직접 계산하도록 구현)
        recommendations = PolicyEngine.get_available_recommendations(
            schedule["business_hours"],
            schedule["booked_slots"],
            duration
        )
        rec_text = " / ".join(recommendations)
        if not rec_text:
            rec_text = "추천 가능한 시간대를 찾지 못했습니다. 다른 날짜를 알려주시면 다시 확인해드릴게요."
        response = f"죄송합니다 고객님, {check['reason']}\n대신 현재 예약 가능한 시간대는 다음과 같습니다.\n{rec_text}"
        return {
            "is_bookable": False,
            "booking_status": "rejected",
            "response_draft": response,
            "next_action": "notify_failure",
            "policy_check_results": {
                "source": schedule["source"],
                "business_hours": schedule["business_hours"],
                "booked_slots": schedule["booked_slots"],
                "reason": check["reason"],
            },
        }


def change_node(state: ReservationState):
    """예약 변경 요청을 처리하고 백엔드 예약을 업데이트."""
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
    slots, customer_lookup = _enrich_slots_with_customer(slots, state)
    name = (slots.name if slots else None) or _extract_name_hint(user_input)
    phone_num = (slots.phone_num if slots else None) or _extract_phone_hint(user_input)
    reserve_date = (slots.reserve_date if slots else None) or (_extract_date_tokens(user_input)[0] if _extract_date_tokens(user_input) else None)
    reserve_time = (slots.reserve_time if slots else None) or (_extract_time_tokens(user_input)[0] if _extract_time_tokens(user_input) else None)
    service = _get_service_display_name(slots.service_code) if slots and slots.service_code else _extract_service_display_from_text(user_input)

    candidates = backend_client.find_reservations(
        name=name,
        phone_num=phone_num,
        reserve_date=reserve_date,
        reserve_time=reserve_time,
        service=service,
    )
    matched = _unique_or_none(candidates)

    if matched is None:
        if not candidates:
            return {
                "booking_status": "N/A",
                "next_action": "ask_followup",
                "response_draft": _build_change_followup(),
                "policy_check_results": {"matched_reservations": []},
            }

        return {
            "booking_status": "N/A",
            "next_action": "ask_followup",
            "response_draft": (
                f"{CHANGE_MESSAGE.strip()}\n"
                "여러 예약이 검색되어 하나로 특정할 수 없습니다.\n"
                "예약자 성함과 기존 예약 날짜/시간을 더 정확히 알려주세요."
            ),
            "policy_check_results": {"matched_reservations": candidates},
        }

    extracted_dates = _extract_date_tokens(user_input)
    extracted_times = _extract_time_tokens(user_input)
    if len(extracted_dates) < 2 or len(extracted_times) < 2:
        return {
            "booking_status": "pending_review",
            "next_action": "ask_followup",
            "response_draft": (
                f"{CHANGE_MESSAGE.strip()}\n"
                "기존 예약을 찾았습니다.\n"
                f"{_candidate_summary_lines([matched])}\n"
                "변경 희망 일정(새 날짜/시간)을 알려주시면 바로 반영하겠습니다."
            ),
            "policy_check_results": {"matched_reservation": matched},
        }

    new_reserve_date = extracted_dates[-1]
    new_reserve_time = extracted_times[-1]

    if not new_reserve_date or not new_reserve_time:
        return {
            "booking_status": "pending_review",
            "next_action": "ask_followup",
            "response_draft": (
                f"{CHANGE_MESSAGE.strip()}\n"
                "기존 예약을 찾았습니다.\n"
                f"{_candidate_summary_lines([matched])}\n"
                "변경 희망 일정(새 날짜/시간)을 알려주시면 바로 반영하겠습니다."
            ),
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
            "policy_check_results": {
                "matched_reservation": matched,
                "schedule_error": schedule,
            },
        }

    matched_reserve_time = str(matched.get("reserve_time", ""))
    booked_slots = [
        slot
        for slot in schedule["booked_slots"]
        if str(slot.get("reserve_time", "")) != matched_reserve_time
    ]

    validation = PolicyEngine.validate_reservation(
        new_reserve_date,
        new_reserve_time,
        duration_min,
        booked_slots,
        business_hours=schedule["business_hours"],
    )

    if not validation["valid"]:
        recommendations = PolicyEngine.get_available_recommendations(
            schedule["business_hours"],
            booked_slots,
            duration_min,
        )
        rec_text = " / ".join(recommendations) if recommendations else "추천 가능한 시간대를 찾지 못했습니다."
        return {
            "booking_status": "rejected",
            "next_action": "ask_followup",
            "response_draft": (
                f"{CHANGE_MESSAGE.strip()}\n"
                f"죄송합니다. {validation['reason']}\n"
                f"대신 가능한 시간대는 다음과 같습니다.\n{rec_text}"
            ),
            "policy_check_results": {
                "matched_reservation": matched,
                "business_hours": schedule["business_hours"],
                "booked_slots": booked_slots,
                "reason": validation["reason"],
            },
        }

    new_reserve_time_range = (
        f"{new_reserve_time}-{(datetime.strptime(new_reserve_time, '%H:%M') + timedelta(minutes=duration_min)).strftime('%H:%M')}"
    )
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
            "policy_check_results": {
                "matched_reservation": matched,
                "update_result": update_result,
            },
        }

    response = (
        f"{CHANGE_MESSAGE.strip()}\n"
        "기존 예약이 변경되었습니다.\n"
        f"- 예약자: {matched.get('name')}\n"
        f"- 예약 ID: {matched.get('id')}\n"
        f"- 변경 후 일정: {new_reserve_date} {new_reserve_time_range}\n"
        f"- 처리 상태: {'backend' if update_result.get('source') == 'backend' else 'mock'}"
    )
    return {
        "booking_status": "updated",
        "next_action": "notify_success",
        "response_draft": response,
        "policy_check_results": {
            "matched_reservation": matched,
            "update_result": update_result,
            "business_hours": schedule["business_hours"],
            "booked_slots": booked_slots,
        },
    }

def cancel_node(state: ReservationState):
    """예약 취소 요청을 처리하고 백엔드에서 예약을 삭제."""
    print("--- [NODE] Cancel Node ---")

    intent = _intent_to_str(state.get("intent", ""))
    if intent != "cancel":
        return {
            "booking_status": "N/A",
            "next_action": "respond_only",
            "response_draft": build_non_booking_response(intent),
        }

    user_input = state.get("user_input", "")
    slots = state.get("slots")
    slots, customer_lookup = _enrich_slots_with_customer(slots, state)
    name = (slots.name if slots else None) or _extract_name_hint(user_input)
    phone_num = (slots.phone_num if slots else None) or _extract_phone_hint(user_input)
    reserve_date = (slots.reserve_date if slots else None) or (_extract_date_tokens(user_input)[0] if _extract_date_tokens(user_input) else None)
    reserve_time = (slots.reserve_time if slots else None) or (_extract_time_tokens(user_input)[0] if _extract_time_tokens(user_input) else None)
    service = _get_service_display_name(slots.service_code) if slots and slots.service_code else _extract_service_display_from_text(user_input)

    candidates = backend_client.find_reservations(
        name=name,
        phone_num=phone_num,
        reserve_date=reserve_date,
        reserve_time=reserve_time,
        service=service,
    )
    matched = _unique_or_none(candidates)

    if matched is None:
        if not candidates:
            return {
                "booking_status": "N/A",
                "next_action": "ask_followup",
                "response_draft": _build_cancel_followup(),
                "policy_check_results": {"matched_reservations": []},
            }

        return {
            "booking_status": "N/A",
            "next_action": "ask_followup",
            "response_draft": (
                f"{CANCEL_MESSAGE.strip()}\n"
                "여러 예약이 검색되어 하나로 특정할 수 없습니다.\n"
                "예약자 성함과 예약 날짜/시간을 더 정확히 알려주세요."
            ),
            "policy_check_results": {"matched_reservations": candidates},
        }

    delete_result = backend_client.delete_reservation(int(matched["id"]))
    if not delete_result.get("success", True):
        return {
            "booking_status": "backend_error",
            "next_action": delete_result.get("next_action", "human_review"),
            "response_draft": "예약 취소 처리 중 오류가 발생했어요. 잠시 후 다시 시도하거나 사장님 확인이 필요합니다.",
            "policy_check_results": {
                "matched_reservation": matched,
                "delete_result": delete_result,
            },
        }

    response = (
        f"{CANCEL_MESSAGE.strip()}\n"
        "예약이 취소되었습니다.\n"
        f"- 예약자: {matched.get('name')}\n"
        f"- 예약 ID: {matched.get('id')}\n"
        f"- 처리 상태: {'backend' if delete_result.get('source') == 'backend' else 'mock'}"
    )
    return {
        "booking_status": "cancelled",
        "next_action": "notify_success",
        "response_draft": response,
        "policy_check_results": {
            "matched_reservation": matched,
            "delete_result": delete_result,
        },
    }

def payment_node(state: ReservationState):
    """입금 확인 및 환불 요청을 처리하고 백엔드 결제 상태를 업데이트."""
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
    name = (slots.name if slots else None) or _extract_name_hint(user_input)
    phone_num = (slots.phone_num if slots else None) or _extract_phone_hint(user_input)
    reserve_date = (slots.reserve_date if slots else None) or (_extract_date_tokens(user_input)[0] if _extract_date_tokens(user_input) else None)
    reserve_time = (slots.reserve_time if slots else None) or (_extract_time_tokens(user_input)[0] if _extract_time_tokens(user_input) else None)
    service = _get_service_display_name(slots.service_code) if slots and slots.service_code else _extract_service_display_from_text(user_input)
    is_refund_request = _is_refund_request(user_input)

    candidates = backend_client.find_reservations(
        name=name,
        phone_num=phone_num,
        reserve_date=reserve_date,
        reserve_time=reserve_time,
        service=service,
        visit_status=None if is_refund_request else "PENDING",
        payment_status="PAID" if is_refund_request else "PENDING",
    )
    matched = _unique_or_none(candidates)

    if matched is None:
        if not candidates:
            return {
                "booking_status": "N/A",
                "next_action": "ask_followup",
                "response_draft": _build_payment_followup(),
                "policy_check_results": {"matched_reservations": []},
            }

        return {
            "booking_status": "N/A",
            "next_action": "ask_followup",
            "response_draft": (
                f"{PAYMENT_MESSAGE.strip()}\n"
                "대상 예약이 여러 건 검색되어 하나로 특정할 수 없습니다.\n"
                "예약자 성함과 예약 날짜/시간을 더 정확히 알려주세요."
            ),
            "policy_check_results": {"matched_reservations": candidates},
        }

    if is_refund_request:
        refund_result = backend_client.refund_payment(int(matched["id"]))
        if not refund_result.get("success", True):
            return {
                "booking_status": "backend_error",
                "next_action": refund_result.get("next_action", "human_review"),
                "response_draft": "환불 처리 중 오류가 발생했어요. 잠시 후 다시 시도하거나 사장님 확인이 필요합니다.",
                "policy_check_results": {
                    "matched_reservation": matched,
                    "refund_result": refund_result,
                },
            }

        response = (
            f"{PAYMENT_MESSAGE.strip()}\n"
            "환불 처리 완료되었습니다.\n"
            f"- 예약자: {matched.get('name')}\n"
            f"- 예약 ID: {matched.get('id')}\n"
            f"- 처리 상태: {'backend' if refund_result.get('source') == 'backend' else 'mock'}"
        )
        return {
            "booking_status": "payment_refunded",
            "next_action": "notify_success",
            "response_draft": response,
            "policy_check_results": {
                "matched_reservation": matched,
                "refund_result": refund_result,
            },
        }

    payment_key = _extract_payment_key(user_input)
    amount = _extract_amount_from_text(user_input)
    if amount is None:
        amount = backend_client.get_shop_info().get("deposit_amount")

    if not payment_key:
        return {
            "booking_status": "pending_review",
            "next_action": "ask_followup",
            "response_draft": (
                f"{PAYMENT_MESSAGE.strip()}\n"
                "입금 확인 대상 예약을 찾았습니다.\n"
                f"{_candidate_summary_lines([matched])}\n"
                "현재 메시지에는 결제 키가 없어 자동 결제 확정은 아직 못했어요.\n"
                "입금자명, 예약자 성함, 입금 금액, 결제 키가 있다면 함께 알려주세요."
            ),
            "policy_check_results": {
                "matched_reservation": matched,
                "matched_reservations": candidates,
            },
        }

    payment_payload = {
        "payment_status": "PAID",
        "payment_key": payment_key,
        "amount": amount,
    }
    update_result = backend_client.update_payment(int(matched["id"]), payment_payload)
    if not update_result.get("success", True):
        return {
            "booking_status": "backend_error",
            "next_action": update_result.get("next_action", "human_review"),
            "response_draft": "결제 상태 반영 중 오류가 발생했어요. 잠시 후 다시 시도하거나 사장님 확인이 필요합니다.",
            "policy_check_results": {
                "matched_reservation": matched,
                "update_result": update_result,
            },
        }

    response = (
        f"{PAYMENT_MESSAGE.strip()}\n"
        "입금 확인이 완료되었습니다.\n"
        f"- 예약자: {matched.get('name')}\n"
        f"- 예약 ID: {matched.get('id')}\n"
        f"- 결제 금액: {amount}원\n"
        f"- 처리 상태: {'backend' if update_result.get('source') == 'backend' else 'mock'}"
    )
    return {
        "booking_status": "payment_confirmed",
        "next_action": "notify_success",
        "response_draft": response,
        "policy_check_results": {
            "matched_reservation": matched,
            "update_result": update_result,
        },
    }

def response_node(state: ReservationState):
    """response_draft가 없으면 intent별 기본 응답으로 채워 최종 응답을 확정."""
    print("--- [NODE] Response Draft ---")

    response_draft = state.get("response_draft")

    if response_draft:
        return {"response_draft": response_draft}

    intent = _intent_to_str(state.get("intent", "unknown"))

    if intent == "booking":
        shop_info = backend_client.get_shop_info()
        booking_form_text = _resolve_shop_text(shop_info, "booking_form_text", BOOKING_FORM_GUIDE)
        return {"response_draft": booking_form_text}

    return {"response_draft": build_non_booking_response(intent)}
