from agent.graph.state import ReservationState

def route_after_intake(state: ReservationState):
    """Intake 노드 이후 어디로 갈지 결정"""
    if state["next_action"] == "ask_followup":
        return "response"
    return "booking"

def route_after_booking(state: ReservationState):
    """Booking 노드 이후 어디로 갈지 결정"""
    return "response"
