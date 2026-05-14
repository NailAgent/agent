from agent.graph.state import ReservationState

def _intent_to_str(intent) -> str:
    """Normalize intent value from Enum or string to plain string."""
    return intent.value if hasattr(intent, "value") else str(intent or "")

def route_after_intake(state: ReservationState):
    """Intake node decides where to go next."""
    intent = _intent_to_str(state.get("intent", ""))

    if intent == "change":
        return "change"

    if intent == "cancel":
        return "cancel"

    if intent == "payment":
        return "payment"

    if intent not in {"booking", "greeting", "inquiry", "unknown"}:
        return "response"

    if intent == "booking":
        if state.get("missing_fields") and len(state["missing_fields"]) > 0:
            return "response" 
        else:
            return "booking"

    return "response"

def route_after_booking(state: ReservationState):
    """Booking node decides where to go next."""
    return "response"
