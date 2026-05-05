from agent.graph.state import ReservationState
from agent.agents.intake_agent import IntakeAgent
from agent.tools.policy_engine import PolicyEngine
from agent.agents.constants import WELCOME_MESSAGE, BOOKING_FORM_GUIDE

# Intake Agent Instance
intake_agent = IntakeAgent()

def intake_node(state: ReservationState):
    """Analyzes user input and extracts information"""
    print("--- [NODE] Intake Agent ---")
    user_input = state["user_input"].strip()
    
    if not user_input or user_input in ["안녕", "안녕하세요", "시작"]:
        return {"intent": "greeting", "response_draft": WELCOME_MESSAGE, "next_action": "ask_followup"}

    result = intake_agent.run(user_input)
    missing_count = len(result.missing_fields)
    
    if result.intent == "booking" and missing_count >= 3:
        return {
            "intent": "booking", "slots": result.slots, "missing_fields": result.missing_fields,
            "next_action": "ask_followup", "response_draft": BOOKING_FORM_GUIDE
        }
    
    return {
        "intent": result.intent, "slots": result.slots, "missing_fields": result.missing_fields,
        "next_action": "ask_followup" if result.need_followup else "validate_booking",
        "response_draft": result.followup_question if result.need_followup else ""
    }

def booking_node(state: ReservationState):
    """Backend-integrated node that checks reservation status and calculates available times"""
    print("--- [NODE] Booking Logic (Backend Integration) ---")
    slots = state["slots"]
    intent = state.get("intent", "")

    if intent != "booking" or not slots.reserve_date or not slots.reserve_time:
        return {"is_bookable": False, "next_action": "ask_followup"}
    
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
    return {"response_draft": state["response_draft"]}
