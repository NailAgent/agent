from langgraph.graph import StateGraph, END
from agent.graph.state import ReservationState
from agent.graph.nodes import intake_node, booking_node, response_node
from agent.graph.router import route_after_intake, route_after_booking

def create_workflow():
    """LangGraph workflow assembly"""
    
    # 1. Initialize graph
    workflow = StateGraph(ReservationState)

    # 2. Add nodes
    workflow.add_node("intake", intake_node)
    workflow.add_node("booking", booking_node)
    workflow.add_node("response", response_node)

    # 3. Connect edges (Define flow)
    workflow.set_entry_point("intake")

    # Conditional routing after intake
    workflow.add_conditional_edges(
        "intake",
        route_after_intake,
        {
            "response": "response",
            "booking": "booking"
        }
    )

    # Move to response after booking
    workflow.add_edge("booking", "response")

    # End after response
    workflow.add_edge("response", END)

    # 4. Compile
    return workflow.compile()

# Executable app instance
app = create_workflow()
