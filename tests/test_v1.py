import sys
import os
from dotenv import load_dotenv

# .env 로드
load_dotenv()

# 프로젝트 루트 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.graph.workflow import app
from agent.agents.schema import BookingSlots

def simulate_conversation(scenario_name: str, turns: list):
    """simulate conversation"""
    print(f"\n{'='*60}")
    print(f"[SCENARIO]: {scenario_name}")
    print(f"{'='*60}")
    
    # 초기 상태 설정
    state = {
        "user_input": "",
        "history": [],
        "slots": BookingSlots(),
        "missing_fields": [],
        "response_draft": ""
    }
    
    for i, user_input in enumerate(turns):
        print(f"\n[Turn {i+1}]")
        print(f"[USER]: {user_input}")
        
        # update user input
        state["user_input"] = user_input
        
        # excute graph
        state = app.invoke(state)
        
        print(f"[AGENT]: \n{state['response_draft']}")
        print(f"--- (Intent: {state.get('intent')}, Status: {state.get('booking_status', 'N/A')}) ---")

    print(f"\n{'='*60}\n")

if __name__ == "__main__":
    # Scenario 1: Standard booking flow (greeting -> request form -> submit form)
    simulate_conversation(
        "Standard Booking Flow",
        [
            "안녕하세요",                          # 1. 처음 들어옴 (환영 메시지 기대)
            "예약 문의하고 싶어요!",               # 2. 의도 표현 (예약 양식/정책 안내 기대)
            """
            - *성함: 김지수
            - *전화번호 (010-0000-0000): 010-1234-5678
            - *젤제거 유무(O/X): O
            - *예약 희망 날짜 (형식: 2026-04-12): 2026-05-07
            - *예약 희망 시간 (형식: 18:00): 17:00
            - *원하시는 시술 종류: 젤네일
            - *과거 방문경험(O/X): X
            """                                   # 3. 양식 제출 (예약 확정 안내 기대)
        ]
    )

    # Scenario 2: Direct booking 
    simulate_conversation(
        "Direct Booking",
        [
            "내일 오후 3시 김지수 010-1111-2222 젤네일 예약요. 제거는 없어요. 처음 가요." 
            # 한 번에 다 말하면 바로 예약 검증으로 가야 함
        ]
    )
    
    # Scenario 3: Policy Violation Case
    simulate_conversation(
        "Policy Violation Case",
        [
            "예약 문의",
            """
            - *성함: 이민호
            - *전화번호: 010-9999-8888
            - *젤제거 유무: X
            - *예약 희망 날짜: 2024-05-06 (월요일)
            - *예약 희망 시간: 14:00
            - *원하시는 시술 종류: 젤네일
            - *과거 방문경험: O
            """
        ]
    )
