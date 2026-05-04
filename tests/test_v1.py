import sys
import os
from dotenv import load_dotenv

# 프로젝트 루트 경로 추가 (모듈 임포트용)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.graph.workflow import app
from agent.agents.schema import BookingSlots

# .env 로드
load_dotenv()

def run_test(scenario_name: str, user_input: str):
    print(f"\n{'='*50}")
    print(f"🎬 TEST SCENARIO: {scenario_name}")
    print(f"💬 INPUT: {user_input}")
    print(f"{'='*50}")
    
    # 그래프 실행 초기 상태 설정
    initial_state = {
        "user_input": user_input,
        "history": [],
        "slots": BookingSlots(), # 빈 슬롯으로 시작
        "missing_fields": []
    }
    
    # 그래프 실행
    final_state = app.invoke(initial_state)
    
    print(f"\n[Output Analysis]")
    print(f"1. Detected Intent: {final_state.get('intent')}")
    print(f"2. Slots Found: {final_state.get('slots')}")
    print(f"3. Next Action: {final_state.get('next_action')}")
    print(f"4. Final Status: {final_state.get('booking_status', 'N/A')}")
    print(f"\n[AGENT RESPONSE]:\n{final_state.get('response_draft')}")
    print(f"{'='*50}\n")

if __name__ == "__main__":
    # 시나리오 1: 정보가 완벽한 정상 예약 (화요일 예약 가정)
    run_test(
        "Happy Path (Full Info)", 
        "김지수, 010-1234-5678, 내일(2024-05-07) 오후 3시에 젤네일 예약하고 싶어요. 제거는 없어요."
    )
    
    # 시나리오 2: 정보가 누락된 경우 (연락처 없음)
    run_test(
        "Missing Info (No Phone)", 
        "내일 오후 3시에 젤네일 예약할게요. 김지수입니다."
    )
    
    # 시나리오 3: 정책 위반 (월요일 휴무일 예약 - 2024-05-06은 월요일)
    run_test(
        "Policy Rejection (Monday)", 
        "김지수, 010-1234-5678, 오늘(2024-05-06) 오후 5시에 젤네일 가능할까요?"
    )
