from enum import Enum
from typing import Optional, List

from pydantic import BaseModel, Field


class BookingSlots(BaseModel):
    """Structure for nail shop booking information."""

    name: Optional[str] = Field(None, description="The customer's name")
    phone_num: Optional[str] = Field(None, description="The customer's phone number (e.g., 010-1234-5678)")
    off_removal: Optional[bool] = Field(None, description="Whether the customer needs old gel removal (O/X)")
    reserve_date: Optional[str] = Field(None, description="The requested reservation date (YYYY-MM-DD)")
    reserve_time: Optional[str] = Field(None, description="The requested reservation time (HH:MM)")
    service_code: Optional[str] = Field(None, description="The type of service (e.g., GEL_BASIC, GEL_NAIL, PEDICURE)")
    past_visit: Optional[bool] = Field(None, description="Whether the customer has visited before (O/X)")

class Intent(str, Enum):
    """Allowed intent labels returned by the Intake Agent."""

    GREETING = "greeting"  # 인삿말 출력
    BOOKING = "booking"  # 예약 생성 처리
    INQUIRY = "inquiry"  # 고정 안내 응답
    CHANGE = "change"  # 예약 변경 처리
    CANCEL = "cancel"  # 예약 취소 처리
    PAYMENT = "payment"  # 결제 확인 처리
    UNKNOWN = "unknown"  # 재질문


class IntakeResult(BaseModel):
    """Result of the initial message analysis by the Intake Agent."""

    intent: Intent = Field(..., description="The detected intent (Allowed values: greeting, booking, inquiry, change, cancel, payment, unknown.)")
    slots: BookingSlots = Field(..., description="Extracted booking information")
    missing_fields: List[str] = Field(default_factory=list, description="List of required fields that are missing")
    uncertain_fields: List[str] = Field(default_factory=list, description="List of fields that were extracted but may be ambiguous or uncertain")
    need_followup: bool = Field(..., description="Whether we need to ask the user for more information")
    followup_question: Optional[str] = Field(None, description="A natural language question to ask for missing info")
