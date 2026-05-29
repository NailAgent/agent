from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import InMemorySaver

from agent.graph.state import ReservationState
from agent.graph.nodes import (
    intake_node,
    booking_node,
    change_node,
    cancel_node,
    payment_node,
    response_node,
)
from agent.graph.router import route_after_intake


def create_workflow():
    """LangGraph workflow assembly"""

    # 1. 워크플로우(그래프) 생성
    workflow = StateGraph(ReservationState)

    # 2. 노드(작업자) 배치
    workflow.add_node("intake", intake_node)
    workflow.add_node("booking", booking_node)
    workflow.add_node("change", change_node)
    workflow.add_node("cancel", cancel_node)
    workflow.add_node("payment", payment_node)
    workflow.add_node("response", response_node)

    # 3. Connect edges (Define flow)
    workflow.set_entry_point("intake")

    # 4. Conditional Edge 연결
    # Conditional routing after intake
    workflow.add_conditional_edges(
        "intake",
        route_after_intake,
        {
            "response": "response",
            "booking": "booking",
            "change": "change",
            "cancel": "cancel",
            "payment": "payment",
        }
    )

    # 3. Edge 연결
    # Move to response after booking
    workflow.add_edge("booking", "response")
    workflow.add_edge("change", "response")
    workflow.add_edge("cancel", "response")
    workflow.add_edge("payment", "response")

    # End after response
    workflow.add_edge("response", END)

    # 4. Compile (최종 에이전트 생성)
    return workflow.compile(checkpointer=InMemorySaver())

# Executable app instance
app = create_workflow()
