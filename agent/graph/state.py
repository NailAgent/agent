from typing import List, NotRequired, Optional, TypedDict
from agent.agents.schema import BookingSlots

def merge_slots(existing: BookingSlots, new: BookingSlots) -> BookingSlots:
    """Helper to merge new slot information into existing slots."""
    # Keep previously known values unless the new payload provides an update.
    if existing is None:
        return new
    if new is None:
        return existing

    merged = existing.model_dump() if hasattr(existing, "model_dump") else existing.dict()
    incoming = new.model_dump() if hasattr(new, "model_dump") else new.dict()
    for key, value in incoming.items():
        if value is not None:
            merged[key] = value
    return BookingSlots(**merged)

class ReservationState(TypedDict):
    """The shared state for the reservation workflow."""
    # Input/Output
    user_input: str
    response_draft: str
    
    # Analysis results
    intent: str
    slots: BookingSlots
    missing_fields: List[str]
    kakao_user_id: str
    plusfriend_user_key: str
    pending_intent: NotRequired[Optional[str]]
    pending_missing_fields: NotRequired[List[str]]
    pending_followup_question: NotRequired[Optional[str]]
    
    # Decisions
    is_bookable: bool
    booking_status: str # 'pending', 'confirmed', 'rejected'
    next_action: str # 'ask_followup', 'validate_booking', 'notify_success'
    
    # Policy/Logic results
    policy_check_results: dict

    # Booking ID (set after reservation created, used for payment verification)
    booking_id: NotRequired[Optional[int]]

    # Toss orderId (booking_{id}_{timestamp}, set after reservation created, used for payment verification)
    order_id: NotRequired[Optional[str]]

    # History
    history: List[dict]
