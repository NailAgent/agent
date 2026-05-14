import re

from agent.graph.state import ReservationState, merge_slots
from agent.agents.intake_agent import IntakeAgent
from agent.tools.backend_client import BackendClient
from agent.tools.policy_engine import PolicyEngine
from agent.agents.constants import (
    BOOKING_FORM_GUIDE,
    CANCEL_FALLBACK_MESSAGE,
    CHANGE_FALLBACK_MESSAGE,
    INQUIRY_FALLBACK_MESSAGE,
    BOOKING_MISSING_DATETIME_MESSAGE,
    PAYMENT_FALLBACK_MESSAGE,
    UNKNOWN_FALLBACK_MESSAGE,
    WELCOME_MESSAGE,
)

# Intake Agent Instance
intake_agent = IntakeAgent()
backend_client = BackendClient()

def _intent_to_str(intent) -> str:
    """Normalize intent value from Enum or string to plain string."""
    return intent.value if hasattr(intent, "value") else str(intent or "")

def build_non_booking_response(intent: str) -> str:
    """Build a v1 fallback response for intents without dedicated nodes yet."""

    # v1: Only the booking flow has a dedicated node in v1.
    # v2: Route change/cancel/payment to dedicated nodes instead of returning fallback messages.
    responses = {
        "greeting": WELCOME_MESSAGE,
        "inquiry": INQUIRY_FALLBACK_MESSAGE,
        "change": CHANGE_FALLBACK_MESSAGE,
        "cancel": CANCEL_FALLBACK_MESSAGE,
        "payment": PAYMENT_FALLBACK_MESSAGE,
        "unknown": UNKNOWN_FALLBACK_MESSAGE,
    }

    return responses.get(intent, UNKNOWN_FALLBACK_MESSAGE)


def _get_service_display_name(service_code: str) -> str:
    """Helper to map service code to Korean name for searching."""
    service_map = {
        "GEL_BASIC": "기본네일",
        "GEL_NAIL": "젤네일",
        "PEDICURE": "페디큐어",
    }
    return service_map.get(service_code, service_code)


def _candidate_summary_lines(candidates: list[dict]) -> str:
    if not candidates:
        return ""
    return "\n".join(f"- {backend_client.format_reservation_summary(item)}" for item in candidates[:3])


def _extract_backend_status(reservation_result: dict) -> str:
    response = reservation_result.get("response") or {}
    status = response.get("status") or reservation_result.get("status_code")
    if status:
        return f"HTTP {status}"
    return "HTTP 상태 미상"

def intake_node(state: ReservationState):
    """Analyzes user input and extracts information with multi-turn memory."""
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
        return {
            "intent": "booking", 
            "slots": merged_slots, 
            "missing_fields": missing_fields,
            "is_bookable": False, 
            "booking_status": "N/A", 
            "next_action": "ask_followup", 
            "response_draft": BOOKING_FORM_GUIDE
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
    """Backend-integrated node that checks reservation status and calculates available times"""
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
        )
        reservation_result = backend_client.create_reservation(reservation_payload)
        reserve_time_range = reservation_payload["reserve_time"]
        backend_status = _extract_backend_status(reservation_result)
        base_message = shop_info["booking_message_text"].strip()
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
    """Handle reservation change requests using shared slots."""
    print("--- [NODE] Change Node ---")

    intent = _intent_to_str(state.get("intent", ""))
    if intent != "change":
        return {
            "booking_status": "N/A",
            "next_action": "respond_only",
            "response_draft": build_non_booking_response(intent),
        }

    slots = state.get("slots")
    name = slots.name if slots else None
    reserve_date = slots.reserve_date if slots else None
    reserve_time = slots.reserve_time if slots else None
    service = _get_service_display_name(slots.service_code) if slots and slots.service_code else None

    candidates = backend_client.find_reservations(
        name=name,
        reserve_date=reserve_date,
        reserve_time=reserve_time,
        service=service,
    )

    if not candidates:
        return {
            "booking_status": "N/A",
            "next_action": "ask_followup",
            "response_draft": (
                f"{CHANGE_FALLBACK_MESSAGE.strip()}\n"
                "기존 예약자 성함과 기존 예약 날짜/시간을 알려주시면 변경 가능 여부를 확인해드릴게요."
            ),
            "policy_check_results": {"matched_reservations": []},
        }

    matched_summary = _candidate_summary_lines(candidates)
    requested_date = reserve_date or "새 날짜"
    requested_time = reserve_time or "새 시간"
    response = (
        f"{CHANGE_FALLBACK_MESSAGE.strip()}\n"
        "기존 예약을 찾았습니다.\n"
        f"{matched_summary}\n"
        f"변경 희망 일정: {requested_date} {requested_time}\n"
        "현재 자동 변경 API는 준비 중이라 사장님 확인이 필요합니다."
    )
    return {
        "booking_status": "pending_review",
        "next_action": "notify_owner",
        "response_draft": response,
        "policy_check_results": {"matched_reservations": candidates},
    }


def cancel_node(state: ReservationState):
    """Handle reservation cancel requests using shared slots."""
    print("--- [NODE] Cancel Node ---")

    intent = _intent_to_str(state.get("intent", ""))
    if intent != "cancel":
        return {
            "booking_status": "N/A",
            "next_action": "respond_only",
            "response_draft": build_non_booking_response(intent),
        }

    slots = state.get("slots")
    name = slots.name if slots else None
    reserve_date = slots.reserve_date if slots else None
    reserve_time = slots.reserve_time if slots else None
    service = _get_service_display_name(slots.service_code) if slots and slots.service_code else None

    candidates = backend_client.find_reservations(
        name=name,
        reserve_date=reserve_date,
        reserve_time=reserve_time,
        service=service,
    )

    if not candidates:
        return {
            "booking_status": "N/A",
            "next_action": "ask_followup",
            "response_draft": (
                f"{CANCEL_FALLBACK_MESSAGE.strip()}\n"
                "예약자 성함과 기존 예약 날짜/시간을 알려주시면 취소 대상 예약을 찾아드릴게요."
            ),
            "policy_check_results": {"matched_reservations": []},
        }

    matched_summary = _candidate_summary_lines(candidates)
    response = (
        f"{CANCEL_FALLBACK_MESSAGE.strip()}\n"
        "취소 대상 예약을 찾았습니다.\n"
        f"{matched_summary}\n"
        "현재 자동 취소 API는 준비 중이라 사장님 확인 후 처리됩니다."
    )
    return {
        "booking_status": "pending_review",
        "next_action": "notify_owner",
        "response_draft": response,
        "policy_check_results": {"matched_reservations": candidates},
    }


def payment_node(state: ReservationState):
    """Handle deposit/payment confirmations using shared slots."""
    print("--- [NODE] Payment Node ---")

    intent = _intent_to_str(state.get("intent", ""))
    if intent != "payment":
        return {
            "booking_status": "N/A",
            "next_action": "respond_only",
            "response_draft": build_non_booking_response(intent),
        }

    slots = state.get("slots")
    name = slots.name if slots else None
    reserve_date = slots.reserve_date if slots else None
    reserve_time = slots.reserve_time if slots else None
    service = _get_service_display_name(slots.service_code) if slots and slots.service_code else None

    candidates = backend_client.find_reservations(
        name=name,
        reserve_date=reserve_date,
        reserve_time=reserve_time,
        service=service,
        visit_status="PENDING",
    )

    if not candidates:
        return {
            "booking_status": "N/A",
            "next_action": "ask_followup",
            "response_draft": (
                f"{PAYMENT_FALLBACK_MESSAGE.strip()}\n"
                "입금자명과 예약자 성함, 예약 날짜를 함께 알려주시면 대조해드릴게요."
            ),
            "policy_check_results": {"matched_reservations": []},
        }

    matched_summary = _candidate_summary_lines(candidates)
    response = (
        f"{PAYMENT_FALLBACK_MESSAGE.strip()}\n"
        "입금 확인 대상 예약을 찾았습니다.\n"
        f"{matched_summary}\n"
        "현재 자동 입금 검증 API는 준비 중이라 사장님 확인 후 상태가 확정됩니다."
    )
    return {
        "booking_status": "pending_review",
        "next_action": "notify_owner",
        "response_draft": response,
        "policy_check_results": {"matched_reservations": candidates},
    }

def response_node(state: ReservationState):
    print("--- [NODE] Response Draft ---")

    response_draft = state.get("response_draft")

    # non-booking이면 fallback 응답 반환 추가
    if response_draft:
        return {"response_draft": response_draft}

    intent = _intent_to_str(state.get("intent", "unknown"))

    if intent == "booking":
        return {"response_draft": BOOKING_FORM_GUIDE}

    return {"response_draft": build_non_booking_response(intent)}
