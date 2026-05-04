from agent.graph.state import ReservationState
from agent.agents.intake_agent import IntakeAgent
from agent.tools.policy_engine import PolicyEngine
from agent.agents.schema import BookingSlots

# 에이전트 인스턴스 생성
intake_agent = IntakeAgent()

def intake_node(state: ReservationState):
    """사용자 입력을 분석하여 정보를 추출하는 노드"""
    print("--- [NODE] Intake Agent ---")
    user_input = state["user_input"]
    result = intake_agent.run(user_input)
    
    # 기존 슬롯 정보와 새 정보 병합 (V1에서는 단순 업데이트)
    return {
        "intent": result.intent,
        "slots": result.slots,
        "missing_fields": result.missing_fields,
        "next_action": "ask_followup" if result.need_followup else "validate_booking",
        "response_draft": result.followup_question if result.need_followup else ""
    }

def booking_node(state: ReservationState):
    """추출된 정보를 바탕으로 정책을 검토하는 노드"""
    print("--- [NODE] Booking Logic (Policy Engine) ---")
    slots = state["slots"]
    
    # Policy Engine을 통한 시간 및 요일 검증
    check = PolicyEngine.validate_time(slots.reserve_date, slots.reserve_time)
    
    if check["valid"]:
        # 예약 성공 시나리오
        duration = PolicyEngine.calculate_duration(slots.service_code, slots.off_removal)
        response = f"예약이 가능합니다! (소요 시간: 약 {duration}분)\n입금 안내를 도와드릴까요?"
        status = "pending_payment"
        next_action = "notify_success"
    else:
        # 정책 위반 시나리오
        response = f"죄송합니다. {check['reason']}"
        status = "rejected"
        next_action = "notify_failure"
        
    return {
        "is_bookable": check["valid"],
        "booking_status": status,
        "response_draft": response,
        "next_action": next_action
    }

def response_node(state: ReservationState):
    """최종 응답을 정리하는 노드"""
    print("--- [NODE] Response Draft ---")
    # 현재는 각 노드에서 생성한 draft를 그대로 사용하거나 보완함
    return {"response_draft": state["response_draft"]}
