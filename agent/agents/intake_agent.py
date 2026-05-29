from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv
from langchain_core.messages import SystemMessage
from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate
from langchain_openai import ChatOpenAI

from agent.agents.schema import IntakeResult
from agent.agents.intake_agent_deterministic import deterministic_intake

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
- "영업시간 문의드립니다" -> intent: inquiry
- "영업시간이 어떻게 되나요?" -> intent: inquiry
- "오늘 몇시까지 해요?" -> intent: inquiry
- "가격이 어떻게 되나요?" -> intent: inquiry
- "젤네일 얼마예요?" -> intent: inquiry
- "이벤트 있나요?" -> intent: inquiry
- "주차 가능한가요?" -> intent: inquiry
- "어디 있어요?" -> intent: inquiry
- "예약금 보내면 되나요?" -> intent: payment
- "입금했어요" -> intent: payment

- "내일 예약을 모레 3시로 바꿔주세요. 홍길동이에요."
  -> intent: change, name: 홍길동, reserve_date: 모레날짜, reserve_time: 15:00

- "예약 시간 바꾸고 싶어요"
  -> intent: change, name: null, reserve_date: null, reserve_time: null

- "예약 취소하고 싶어요. 김민지입니다."
  -> intent: cancel, name: 김민지

- "예약 취소하고 싶어요"
  -> intent: cancel, name: null

- "내일 오후 3시 홍길동 010-1111-2222 젤네일 예약요. 제거는 없어요. 처음 가요."
  -> intent: booking, name: 홍길동, phone_num: 010-1111-2222, off_removal: false, reserve_date: 내일날짜, reserve_time: 15:00, service_code: GEL_NAIL, past_visit: false

- "남민서 010-1111-2222 2026-05-29 오전 11시 손톱케어 방문X 지인 소개"
  -> intent: booking, name: 남민서, phone_num: 010-1111-2222, off_removal: null, reserve_date: 2026-05-29, reserve_time: 11:00, service_code: GEL_BASIC, past_visit: false, missing_fields: ["off_removal"]

""".strip()


SYSTEM_PROMPT = """
### CRITICAL RULES
- NEVER guess, assume, or infer slot values that are not explicitly mentioned by the customer.
- If a slot value is not clearly stated, set it to null and add to missing_fields.
- Do NOT fill in default values (e.g., do not assume 12:00 if no time is given).
- Only extract what the customer explicitly said.
- "off_removal" must ONLY be set to true or false when the customer explicitly mentions gel removal (젤제거, 오프, 제거, 오프제거, 젤오프). If not mentioned at all, set "off_removal": null and add "off_removal" to missing_fields. NEVER default to false.

IMPORTANT: Do NOT use any tools. Output the JSON directly without ANY explanation or text before/after the JSON. Your entire response must be ONLY the JSON object, nothing else.

Do NOT wrap your response in any outer object like {"output": ...}. Output the JSON directly at the root level.

### ROLE
You are an Intake Agent for a nail shop booking system.
Your job is to classify the customer's message into exactly one of the following intents, and extract booking slots.
Today's date is {{ $now.toFormat('yyyy-MM-dd') }}.

### ALLOWED INTENTS
Use only one of:
1. greeting
2. booking
3. inquiry
4. change
5. cancel
6. payment
7. unknown

### INTENT DEFINITIONS
1. booking: The customer wants to make a new reservation.
    Important: "예약 문의", "예약 문의하고 싶어요", "예약 가능할까요",
    "예약하고 싶어요", "예약 잡고 싶어요", and "애약 문의"
    must be classified as booking, not inquiry.
    Even if the message contains the Korean word "문의", classify it as booking when the customer is asking about making a reservation.

2. inquiry: General questions only, without a reservation request.
    Examples: price, business hours, location, parking, available services.
    Important: Messages containing "문의" that are NOT about making a reservation
    must be classified as inquiry, not booking.
    - "영업시간 문의드립니다" → inquiry
    - "가격 문의드립니다" → inquiry
    - "영업시간이 어떻게 되나요?" → inquiry
    - "가격이 얼마예요?" → inquiry
    Keywords that indicate inquiry: 영업시간, 가격, 위치, 시술 종류, 이벤트

3. change: The customer wants to change an existing reservation.
4. cancel: The customer wants to cancel an existing reservation.
5. payment: The customer talks about deposit, payment, transfer, refund, or payment confirmation.
6. greeting: The customer is only greeting.
7. unknown: Use unknown when the message does not clearly match booking, inquiry, change, cancel, payment, or greeting.
    Important:
    Do NOT classify unclear messages as inquiry.
    Do NOT guess the customer's intent.
    If there is no clear evidence for booking, inquiry, change, cancel, payment, or greeting, return unknown.

### SLOT EXTRACTION
For 'booking' intent, extract:
- name: Customer's name.
- phone_num: Phone number. Standardize to 010-XXXX-XXXX.
- off_removal: ONLY set true/false if customer explicitly mentions gel removal. null if not mentioned.
- reserve_date: Date in YYYY-MM-DD. Interpret relative dates using Current Date.
- reserve_time: Time in HH:MM.
- service_code: One of [GEL_BASIC, GEL_NAIL, PEDICURE].
- past_visit: True if visited before, False if first visit.

For 'change' intent, extract:
- name: Customer's name if mentioned. Leave null if not mentioned.
- reserve_date: New date in YYYY-MM-DD if mentioned. Leave null if not mentioned.
- reserve_time: New time in HH:MM if mentioned. Leave null if not mentioned.
- service_code: New service code if mentioned. Leave null if not mentioned.
- off_removal: New gel removal preference ONLY if explicitly mentioned. Leave null if not mentioned.

For 'cancel' intent, extract:
- name: Customer's name if mentioned. Leave null if not mentioned.

### NORMALIZATION RULES
- 젤네일, 젤 네일, 젤 -> GEL_NAIL
- 기본네일, 기본 네일, 케어, 손톱 케어, 손톱케어 -> GEL_BASIC
- 페디, 페디큐어 -> PEDICURE

### TIME NORMALIZATION
- "N시" -> "N:00" (예: 14시 -> 14:00, 오후 2시 -> 14:00)
- "N시 M분" -> "N:MM" (예: 2시 30분 -> 14:30)
- 오전/오후 변환 적용

### REQUIRED FIELDS FOR BOOKING
name, phone_num, off_removal, reserve_date, reserve_time, service_code, past_visit

### OUTPUT BEHAVIOR
For 'booking' intent:
- Extract all slots. Add missing required fields to missing_fields.
- Set need_followup to True if any required field is missing.
- followup_question is always null.

For 'change' intent:
- Extract name and any new slot fields if mentioned.
- missing_fields is always empty [].
- followup_question is always null.
- need_followup is always false.
- response is always "".

For 'cancel' intent:
- Extract name if mentioned.
- missing_fields is always empty [].
- followup_question is always null.
- need_followup is always false.
- response is always "".

For 'greeting', 'inquiry', 'payment', 'unknown':
- Do not extract slots. missing_fields is always empty [].
- Write response in Korean.

Handle typos, spacing errors, and informal Korean gracefully.


### OUTPUT FORMAT
반드시 아래 JSON을 직접 출력하세요. "output" 키로 감싸지 마세요:

{
  "intent": "",
  "slots": {
    "name": null,
    "phone_num": null,
    "reserve_date": null,
    "reserve_time": null,
    "service_code": null,
    "off_removal": null,
    "past_visit": null
  },
  "missing_fields": [],
  "need_followup": false,
  "followup_question": null,
  "response": ""
}

- greeting/inquiry/payment/unknown → response에 한국어 답변 작성, 나머지 필드 기본값 유지
- booking → 슬롯 추출, 누락 필드는 missing_fields에 추가, followup_question 작성
- change → name과 변경할 슬롯 추출 (언급된 것만), missing_fields/followup_question/response 모두 기본값
- cancel → name 추출 (언급된 경우만), missing_fields/followup_question/response 모두 기본값
""".strip()


def _build_followup_question(missing_fields: list[str]) -> str:
    """누락 슬롯에 대한 followup 질문 생성. LLM 미응답 시 safety net으로도 사용."""
    label_map = {
        "name": "성함",
        "phone_num": "전화번호",
        "off_removal": "젤제거 유무(O/X)",
        "reserve_date": "예약 희망 날짜",
        "reserve_time": "예약 희망 시간",
        "service_code": "원하시는 시술 종류",
        "past_visit": "과거 방문경험(O/X)",
    }
    labels = [label_map.get(f, f) for f in missing_fields]
    if not labels:
        return "예약을 위해 필요한 정보를 조금 더 알려주세요."
    if len(labels) == 1:
        particle = "을" if labels[0].endswith(("음", "함")) else "를"
        return f"예약을 위해 {labels[0]}{particle} 알려주세요."
    return "예약을 위해 다음 정보를 알려주세요: " + ", ".join(labels)


def build_system_prompt() -> str:
    """Build the final system prompt for the Intake Agent."""

    return f"""{SYSTEM_PROMPT}

### FEW-SHOT EXAMPLES
{FEW_SHOT_EXAMPLES}
"""



class IntakeAgent:
    """Agent responsible for analyzing user input and extracting booking information."""

    def __init__(self, model_name: str = "gpt-4o"):
        self.use_llm = bool(os.getenv("OPENAI_API_KEY")) and os.getenv("INTAKE_AGENT_MODE", "llm") != "deterministic"
        self.model_name = model_name

        if self.use_llm:
            self.llm = ChatOpenAI(model=model_name, temperature=0)
            self.structured_llm = self.llm.with_structured_output(IntakeResult)
            self.prompt = ChatPromptTemplate.from_messages(
                [
                    SystemMessage(content=build_system_prompt()),
                    HumanMessagePromptTemplate.from_template("{input}"),
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

        return deterministic_intake(user_input, _build_followup_question)
