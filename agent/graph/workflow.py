from langgraph.graph import StateGraph, END
from agent.graph.state import ReservationState
from agent.graph.nodes import intake_node, booking_node, response_node
from agent.graph.router import route_after_intake, route_after_booking

def create_workflow():
    """LangGraph 워크플로우 조립"""
    
    # 1. 그래프 초기화
    workflow = StateGraph(ReservationState)

    # 2. 노드 추가
    workflow.add_node("intake", intake_node)
    workflow.add_node("booking", booking_node)
    workflow.add_node("response", response_node)

    # 3. 엣지 연결 (흐름 정의)
    workflow.set_entry_point("intake")

    # Intake 이후 조건부 라우팅
    workflow.add_conditional_edges(
        "intake",
        route_after_intake,
        {
            "response": "response",
            "booking": "booking"
        }
    )

    # Booking 이후 Response로 이동
    workflow.add_edge("booking", "response")

    # Response 이후 종료
    workflow.add_edge("response", END)

    # 4. 컴파일
    return workflow.compile()

# 실행용 앱 인스턴스
app = create_workflow()
