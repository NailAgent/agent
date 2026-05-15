from __future__ import annotations

import os
import re
from datetime import datetime, timedelta
from typing import Optional

from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from agent.agents.schema import BookingSlots, IntakeResult, Intent

# 환경 변수 로드
load_dotenv()


def get_current_date() -> str:
    """Return today's local date string for relative date parsing."""
    return datetime.now().strftime("%Y-%m-%d (%A)")


FEW_SHOT_EXAMPLES = """
- "안녕하세요" -> intent: greeting
- "저기요" -> intent: greeting
- "예약 문의" -> intent: booking
- "애약 문의" -> intent: booking
- "가격 얼마예요?" -> intent: inquiry
- "영업시간이 어떻게 되나요?" -> intent: inquiry
- "예약 시간 바꾸고 싶어요" -> intent: change
- "예약 취소하고 싶어요" -> intent: cancel
- "입금했어요" -> intent: payment
- "내일 오후 3시 홍길동 010-1111-2222 젤네일 예약요. 제거는 없어요. 처음 가요."
   -> intent: booking
   -> name: 홍길동
   -> phone_num: 010-1111-2222
   -> off_removal: False
   -> reserve_date: 2026-06-01
   -> reserve_time: 15:00
   -> service_code: GEL_NAIL
   -> past_visit: False
""".strip()


SYSTEM_PROMPT = """
### ROLE
You are an Intake Agent for a nail shop booking system.
Your job is to classify the customer's intent and extract booking slots.

### CURRENT DATE
Current Date: {current_date}

### ALLOWED INTENTS :
Use only one of:
- greeting
- booking
- inquiry
- change
- cancel
- payment
- unknown

### INTENT RULES
- booking: The customer wants to make a new reservation.
  Important: "예약 문의", "예약 문의하고 싶어요", "예약 가능할까요",
  "예약하고 싶어요", "예약 잡고 싶어요", and "애약 문의"
  must be classified as booking, not inquiry.
  Even if the message contains the Korean word "문의", classify it as booking when the customer is asking about making a reservation.

- inquiry: General questions only, without a reservation request.
  Examples: price, business hours, location, parking, available services.

- change: The customer wants to change an existing reservation.
- cancel: The customer wants to cancel an existing reservation.
- payment: The customer talks about deposit, payment, transfer, refund, or payment confirmation.
- greeting: The customer is only greeting.
- unknown: The intent is unclear.

### SLOT EXTRACTION
For booking intent, extract:
- name: Customer's name.
- phone_num: Phone number. Standardize to 010-XXXX-XXXX.
- off_removal: True if gel removal is needed, False if not.
- reserve_date: Date in YYYY-MM-DD. Interpret relative dates using Current Date.
- reserve_time: Time in HH:MM.
- service_code: One of [GEL_BASIC, GEL_NAIL, PEDICURE].
- past_visit: True if visited before, False if first visit.

### NORMALIZATION RULES
Normalize service names:
- 젤네일, 젤 네일, 젤 -> GEL_NAIL
- 기본네일, 기본 네일, 케어, 손톱 케어 -> GEL_BASIC
- 페디, 페디큐어 -> PEDICURE

### REQUIRED FIELDS FOR BOOKING
name, phone_num, off_removal, reserve_date, reserve_time, service_code, past_visit

### OUTPUT BEHAVIOR
If any required booking field is missing:
- Add it to missing_fields.
- Set need_followup to True.
- Write followup_question politely in Korean.

If intent is not booking:
- Do not require booking fields.
- missing_fields should be empty unless the intent is unknown.

Handle typos, spacing errors, and informal Korean gracefully.
""".strip()


def build_system_prompt() -> str:
    """Build the final system prompt for the Intake Agent."""

    return f"""{SYSTEM_PROMPT}

### FEW-SHOT EXAMPLES
{FEW_SHOT_EXAMPLES}
"""


def _extract_first(pattern: str, text: str, flags: int = re.IGNORECASE) -> Optional[str]:
    match = re.search(pattern, text, flags)
    if not match:
        return None
    return match.group(1).strip()


def _normalize_phone(phone: Optional[str]) -> Optional[str]:
    if not phone:
        return None

    digits = re.sub(r"\D", "", phone)
    if len(digits) == 11 and digits.startswith("010"):
        return f"{digits[:3]}-{digits[3:7]}-{digits[7:]}"
    return phone if "-" in phone else None


def _parse_bool_from_text(text: str, positive_patterns: list[str], negative_patterns: list[str]) -> Optional[bool]:
    lowered = text.lower()
    for pattern in negative_patterns:
        if pattern in lowered:
            return False
    for pattern in positive_patterns:
        if pattern in lowered:
            return True
    return None


def _resolve_relative_date(text: str) -> Optional[str]:
    today = datetime.now().date()
    normalized = text.replace(" ", "")

    relative_map = {
        "오늘": 0,
        "내일": 1,
        "모레": 2,
    }
    for keyword, delta in relative_map.items():
        if keyword in normalized:
            return (today + timedelta(days=delta)).strftime("%Y-%m-%d")

    absolute = _extract_first(r"(\d{4}-\d{2}-\d{2})", text)
    return absolute


def _normalize_service_code(text: str) -> Optional[str]:
    normalized = text.replace(" ", "")
    if any(keyword in normalized for keyword in ("페디큐어", "페디")):
        return "PEDICURE"
    if any(keyword in normalized for keyword in ("기본네일", "손톱케어", "기본케어", "케어")):
        return "GEL_BASIC"
    if "젤" in normalized:
        return "GEL_NAIL"
    return None


def _classify_intent(text: str) -> Intent:
    normalized = text.replace(" ", "")

    if any(keyword in normalized for keyword in ("예약변경", "바꾸고싶", "변경", "수정")):
        return Intent.CHANGE
    if any(keyword in normalized for keyword in ("예약취소", "취소하고싶", "취소")):
        return Intent.CANCEL
    if any(keyword in normalized for keyword in ("입금", "결제", "송금", "환불")):
        return Intent.PAYMENT
    if any(keyword in normalized for keyword in ("예약문의", "예약가능", "예약하고싶", "예약잡고", "애약문의")):
        return Intent.BOOKING
    if any(keyword in normalized for keyword in ("안녕", "저기요", "안녕하세요", "하이", "hello")):
        return Intent.GREETING
    if "예약" in normalized:
        return Intent.BOOKING
    if any(keyword in normalized for keyword in ("가격", "영업시간", "위치", "주차", "메뉴", "시술", "얼마")):
        return Intent.INQUIRY
    return Intent.UNKNOWN


def _extract_name(text: str) -> Optional[str]:
    for pattern in (
        r"(?:성함|이름|예약자)\s*[:：]?\s*([가-힣]{2,4})",
        r"([가-힣]{2,4})\s*(?:님)?\s*010-?\d{3,4}-?\d{4}",
        r"^([가-힣]{2,4})\s+(?:\d{4}-\d{2}-\d{2}|01\d-\d{3,4}-\d{4})",
        r"^([가-힣]{2,4})\s+.*?(?:예약|입금|취소|변경)",
        r"성함\s*[:：]?\s*([가-힣]{2,4})",
    ):
        value = _extract_first(pattern, text)
        if value:
            return value
    return None


def _extract_phone(text: str) -> Optional[str]:
    value = _extract_first(r"(01[016789]-?\d{3,4}-?\d{4})", text)
    return _normalize_phone(value)


def _extract_time(text: str) -> Optional[str]:
    value = _extract_first(r"(\d{1,2}:\d{2})", text)
    if not value:
        meridiem_match = re.search(r"(오전|오후)?\s*(\d{1,2})\s*시", text)
        if not meridiem_match:
            return None

        meridiem = meridiem_match.group(1)
        hour = int(meridiem_match.group(2))
        if meridiem == "오후" and hour < 12:
            hour += 12
        if meridiem == "오전" and hour == 12:
            hour = 0
        return f"{hour:02d}:00"

    hour, minute = value.split(":")
    return f"{int(hour):02d}:{int(minute):02d}"


def _extract_off_removal(text: str) -> Optional[bool]:
    explicit = _extract_first(
        r"(?:젤제거\s*유무|젤제거|오프\s*제거)\s*[:：]?\s*([OXox])",
        text,
    )
    if explicit:
        return explicit.upper() == "O"

    explicit = _parse_bool_from_text(
        text,
        positive_patterns=["제거o", "제거있", "오프있", "off있", "있어요", "함", "o"],
        negative_patterns=["제거x", "제거없", "오프없", "없어요", "안해", "x", "no"],
    )
    if explicit is not None:
        return explicit

    normalized = text.replace(" ", "")
    if "제거" in normalized or "오프" in normalized:
        if any(keyword in normalized for keyword in ("없", "안", "x")):
            return False
        return True
    return None


def _extract_past_visit(text: str) -> Optional[bool]:
    explicit = _extract_first(
        r"(?:과거\s*방문경험|방문경험)\s*[:：]?\s*([OXox])",
        text,
    )
    if explicit:
        return explicit.upper() == "O"

    normalized = text.replace(" ", "").lower()
    if any(keyword in normalized for keyword in ("처음가", "첫방문", "처음방문", "처음가요", "첫방")):
        return False
    if any(keyword in normalized for keyword in ("재방문", "방문경험", "가본적", "다시")):
        if any(keyword in normalized for keyword in ("없", "x", "처음")):
            return False
        return True
    return None


def _build_followup_question(missing_fields: list[str]) -> str:
    label_map = {
        "name": "성함",
        "phone_num": "전화번호",
        "off_removal": "젤제거 유무(O/X)",
        "reserve_date": "예약 희망 날짜",
        "reserve_time": "예약 희망 시간",
        "service_code": "원하시는 시술 종류",
        "past_visit": "과거 방문경험(O/X)",
    }

    labels = [label_map.get(field, field) for field in missing_fields]
    if not labels:
        return "예약을 위해 필요한 정보를 조금 더 알려주세요."
    if len(labels) == 1:
        particle = "을" if labels[0].endswith(("음", "함")) else "를"
        return f"예약을 위해 {labels[0]}{particle} 알려주세요."
    return "예약을 위해 다음 정보를 알려주세요: " + ", ".join(labels)


def _deterministic_intake(user_input: str) -> IntakeResult:
    intent = _classify_intent(user_input)
    slots = BookingSlots()
    missing_fields: list[str] = []
    uncertain_fields: list[str] = []
    need_followup = False
    followup_question: Optional[str] = None

    if intent == Intent.BOOKING:
        slots.name = _extract_name(user_input)
        slots.phone_num = _extract_phone(user_input)
        slots.off_removal = _extract_off_removal(user_input)
        slots.reserve_date = _resolve_relative_date(user_input)
        slots.reserve_time = _extract_time(user_input)
        slots.service_code = _normalize_service_code(user_input)
        slots.past_visit = _extract_past_visit(user_input)

        required_fields = {
            "name": slots.name,
            "phone_num": slots.phone_num,
            "off_removal": slots.off_removal,
            "reserve_date": slots.reserve_date,
            "reserve_time": slots.reserve_time,
            "service_code": slots.service_code,
            "past_visit": slots.past_visit,
        }
        missing_fields = [field for field, value in required_fields.items() if value is None]
        need_followup = len(missing_fields) > 0
        if need_followup:
            followup_question = _build_followup_question(missing_fields)

    elif intent == Intent.UNKNOWN:
        need_followup = True
        followup_question = "예약 문의, 예약 변경, 예약 취소, 입금 확인 중 어떤 요청인지 알려주세요."

    return IntakeResult(
        intent=intent,
        slots=slots,
        missing_fields=missing_fields,
        uncertain_fields=uncertain_fields,
        need_followup=need_followup,
        followup_question=followup_question,
    )


class IntakeAgent:
    """Agent responsible for analyzing user input and extracting booking information."""

    def __init__(self, model_name: str = "gpt-4o"):
        self.use_llm = bool(os.getenv("OPENAI_API_KEY")) and os.getenv("INTAKE_AGENT_MODE", "deterministic") == "llm"
        self.model_name = model_name

        if self.use_llm:
            self.llm = ChatOpenAI(model=model_name, temperature=0)
            self.structured_llm = self.llm.with_structured_output(IntakeResult)
            self.prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", build_system_prompt()),
                    ("human", "{input}"),
                ]
            )
            self.chain = self.prompt | self.structured_llm
        else:
            self.llm = None
            self.structured_llm = None
            self.prompt = None
            self.chain = None

    def run(self, user_input: str) -> IntakeResult:
        """Analyze input and return structured results."""

        if self.use_llm and self.chain is not None:
            return self.chain.invoke(
                {
                    "input": user_input,
                    "current_date": get_current_date(),
                }
            )

        return _deterministic_intake(user_input)
