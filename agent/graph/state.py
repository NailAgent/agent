from typing import Annotated, TypedDict, List, Union
from agent.agents.schema import BookingSlots

def merge_slots(existing: BookingSlots, new: BookingSlots) -> BookingSlots:
    """Helper to merge new slot information into existing slots."""
    # We will implement merging logic if needed, or just let the LLM handle it
    # For now, we'll simple return the latest or merge fields manually in nodes
    return new

class ReservationState(TypedDict):
    """The shared state for the reservation workflow."""
    # Input/Output
    user_input: str
    response_draft: str
    
    # Analysis results
    intent: str
    slots: BookingSlots
    missing_fields: List[str]
    
    # Decisions
    is_bookable: bool
    booking_status: str # 'pending', 'confirmed', 'rejected'
    next_action: str # 'ask_followup', 'validate_booking', 'notify_success'
    
    # Policy/Logic results
    policy_check_results: dict
    
    # History
    history: List[dict]
