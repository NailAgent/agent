from agent.graph.state import ReservationState

def _intent_to_str(intent) -> str:
    """Normalize intent value from Enum or string to plain string."""
    return intent.value if hasattr(intent, "value") else str(intent or "")

def route_after_intake(state: ReservationState):
    """Intake node decides where to go next."""
    # If there are missing fields that require a follow-up question

    intent = _intent_to_str(state.get("intent", ""))

    if intent != "booking":
        return "response"

    if state.get("missing_fields") and len(state["missing_fields"]) > 0:
        return "response" 
    # Otherwise, proceed to booking
    return "booking"

    # v2 확장 시 아래 코드 사용
    # if intent == "booking":
    #     if state.get("missing_fields") and len(state["missing_fields"]) > 0:
    #         return "response"
    #     return "booking"

    # if intent == "change":
    #     return "change"

    # if intent == "cancel":
    #     return "cancel"

    # if intent == "payment":
    #     return "payment"

    # return "response"

def route_after_booking(state: ReservationState):
    """Booking node decides where to go next."""
    return "response"
