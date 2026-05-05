from agent.graph.state import ReservationState
from agent.agents.intake_agent import IntakeAgent
from agent.tools.policy_engine import PolicyEngine
from agent.agents.constants import WELCOME_MESSAGE, BOOKING_FORM_GUIDE

# 에이전트 인스턴스 생성
intake_agent = IntakeAgent()

def intake_node(state: ReservationState):
    """사용자 입력을 분석하고, 상황에 맞는 안내(고정 문자열) 또는 추출을 수행하는 노드"""
    print("--- [NODE] Intake Agent ---")
    user_input = state["user_input"].strip()
    
    # 1. 입력이 아예 없거나 인삿말인 경우 초기 환영 메시지 출력
    if not user_input or user_input in ["안녕", "안녕하세요", "시작"]:
        return {
            "intent": "greeting",
            "response_draft": WELCOME_MESSAGE,
            "next_action": "ask_followup"
        }

    # 2. LLM을 통한 의도 및 정보 추출
    result = intake_agent.run(user_input)
    
    # 3. 신규 예약 의도(booking)인데 아직 정보가 거의 없는 경우 -> 고정 예약 양식 출력
    # (필수 필드 중 3개 이상이 비어있으면 양식을 처음 본다고 간주)
    missing_count = len(result.missing_fields)
    
    if result.intent == "booking" and missing_count >= 3:
        return {
            "intent": "booking",
            "slots": result.slots,
            "missing_fields": result.missing_fields,
            "next_action": "ask_followup",
            "response_draft": BOOKING_FORM_GUIDE
        }
    
    # 4. 정보가 충분하거나 추가 질문이 필요한 경우
    return {
        "intent": result.intent,
        "slots": result.slots,
        "missing_fields": result.missing_fields,
        "next_action": "ask_followup" if result.need_followup else "validate_booking",
        "response_draft": result.followup_question if result.need_followup else ""
    }

def booking_node(state: ReservationState):
    """추출된 정보를 바탕으로 정책 검증 및 최종 안내 문자열 생성"""
    print("--- [NODE] Booking Logic (Policy Engine) ---")
    slots = state["slots"]
    intent = state.get("intent", "")

    # 예약 의도가 아니거나 슬롯이 비어있으면 검증 건너뜀
    if intent != "booking" or not slots.reserve_date or not slots.reserve_time:
        return {
            "is_bookable": False,
            "next_action": "ask_followup"
        }
    
    # Policy Engine 검증
    check = PolicyEngine.validate_time(slots.reserve_date, slots.reserve_time)
    
    if check["valid"]:
        duration = PolicyEngine.calculate_duration(slots.service_code, slots.off_removal)
        # 예약 가능 시 고정 안내 문구 반영
        response = f"안녕하세요 고객님, 해당 시간 예약이 가능합니다! (소요 시간: 약 {duration}분)\n입금 안내를 도와드릴까요?"
        status = "pending_payment"
        next_action = "notify_success"
    else:
        # 예약 불가 시 고정 안내 문구 반영
        response = f"죄송합니다 고객님, 해당 시간에 예약이 다 차있는 상태입니다.\n다른 가능한 날짜/시간 있으실까요?\n현재 해당 날짜에 시술 가능한 시간대는 다음과 같습니다.\n10:00-12:30 / 3:00-4:00 / 19:00-22:00"
        status = "rejected"
        next_action = "notify_failure"
        
    return {
        "is_bookable": check["valid"],
        "booking_status": status,
        "response_draft": response,
        "next_action": next_action
    }

def response_node(state: ReservationState):
    """최종 응답 정리"""
    print("--- [NODE] Response Draft ---")
    return {"response_draft": state["response_draft"]}
