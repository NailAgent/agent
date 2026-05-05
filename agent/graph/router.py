from agent.graph.state import ReservationState

def route_after_intake(state: ReservationState):
    """Intake node decides where to go next."""
    # If there are missing fields that require a follow-up question
    if state.get("missing_fields") and len(state["missing_fields"]) > 0:
        return "response" 
    # Otherwise, proceed to booking
    return "booking"

def route_after_booking(state: ReservationState):
    """Booking node decides where to go next."""
    return "response"
