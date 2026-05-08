from agent.graph.state import ReservationState
from agent.agents.intake_agent import IntakeAgent
from agent.tools.policy_engine import PolicyEngine
from agent.agents.constants import (
    BOOKING_FORM_GUIDE,
    CANCEL_FALLBACK_MESSAGE,
    CHANGE_FALLBACK_MESSAGE,
    INQUIRY_FALLBACK_MESSAGE,
    MISSING_RESERVATION_DATETIME_MESSAGE,
    PAYMENT_FALLBACK_MESSAGE,
    UNKNOWN_FALLBACK_MESSAGE,
    WELCOME_MESSAGE,
)

# Intake Agent Instance
intake_agent = IntakeAgent()

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

def intake_node(state: ReservationState):
    """Analyzes user input and extracts information"""
    print("--- [NODE] Intake Agent ---")
    user_input = state["user_input"].strip()
    
    # Empty input cannot be classified by the Intake Agent.
    if not user_input:
        return {
            "intent": "greeting",
            "missing_fields": [],
            "is_bookable": False,
            "booking_status": "N/A",
            "next_action": "respond_only",
            "response_draft": WELCOME_MESSAGE,
        }

    result = intake_agent.run(user_input)
    intent = _intent_to_str(result.intent)
    missing_fields = result.missing_fields
    missing_count = len(missing_fields)
    
    # v1: booking 외 intent에 대한 전용 노드가 없으므로 response_node에서 fallback 응답을 생성
    # v2: change/cancel/payment 노드를 추가하면 router.py에서 해당 노드로 라우팅
    if intent != "booking":
        return {
            "intent": intent, "slots": result.slots, "missing_fields": [],
            "is_bookable": False, "booking_status": "N/A",
            "next_action": "respond_only", "response_draft": "",
        }

    if missing_count >= 3:
        return {
            "intent": "booking", "slots": result.slots, "missing_fields": missing_fields,
            "is_bookable": False, "booking_status": "N/A", 
            "next_action": "ask_followup", "response_draft": BOOKING_FORM_GUIDE
        }
    
    return {
        "intent": "booking", "slots": result.slots, "missing_fields": missing_fields,
        "is_bookable": False, "booking_status": "N/A", 
        "next_action": "ask_followup" if result.need_followup else "validate_booking",
        "response_draft": result.followup_question if result.need_followup else ""
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
    
    # Backend simulation: Replace this with actual API calls
    dummy_backend_data = {
        "date": slots.reserve_date,
        "business_hours": {"start": "10:00", "end": "22:00"},
        "booked_slots": [
            {"start": "11:00", "end": "12:30", "duration_min": 90},
            {"start": "14:00", "end": "15:00", "duration_min": 60}
        ]
    }
    
    # 1. 소요 시간 계산
    duration = PolicyEngine.calculate_duration(slots.service_code, slots.off_removal)
    
    # 2. 예약 가능 여부 검증 (Policy Engine 호출)
    check = PolicyEngine.validate_reservation(
        slots.reserve_date, 
        slots.reserve_time, 
        duration, 
        dummy_backend_data["booked_slots"]
    )
    
    if check["valid"]:
        response = f"안녕하세요 고객님, 해당 시간 예약이 가능합니다! (소요 시간: 약 {duration}분)\n입금 안내를 도와드릴까요?"
        return {"is_bookable": True, "booking_status": "pending_payment", "response_draft": response, "next_action": "notify_success"}
    else:
        # 3. 예약 불가 시 대체 시간 추천 (백엔드 데이터를 기반으로 에이전트가 직접 계산하도록 구현)
        recommendations = PolicyEngine.get_available_recommendations(
            dummy_backend_data["business_hours"],
            dummy_backend_data["booked_slots"],
            duration
        )
        rec_text = " / ".join(recommendations)
        response = f"죄송합니다 고객님, {check['reason']}\n대신 현재 예약 가능한 시간대는 다음과 같습니다.\n{rec_text}"
        return {"is_bookable": False, "booking_status": "rejected", "response_draft": response, "next_action": "notify_failure"}

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
