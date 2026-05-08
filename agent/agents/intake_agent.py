from datetime import datetime
from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from agent.agents.schema import IntakeResult, BookingSlots

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
   -> reserve_date: 2026-05-06
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

class IntakeAgent:
    """Agent responsible for analyzing user input and extracting booking information."""
    
    def __init__(self, model_name: str = "gpt-4o"):
        self.llm = ChatOpenAI(model=model_name, temperature=0)
        self.structured_llm = self.llm.with_structured_output(IntakeResult)

        self.prompt = ChatPromptTemplate.from_messages(
            [
                ("system", build_system_prompt()),
                ("human", "{input}"),
            ])

        self.chain = self.prompt | self.structured_llm

    def run(self, user_input: str) -> IntakeResult:
        """Analyze input and returns structured results."""

        return self.chain.invoke(
            {
                "input": user_input,
                "current_date": get_current_date(),
            }
        )