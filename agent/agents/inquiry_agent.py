from __future__ import annotations

import json
from typing import Any

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

load_dotenv()


class InquiryResult(BaseModel):
    is_trigger: bool       # 실제 질문 없이 문의 의사만 표현한 경우
    answered: bool         # shop_info로 답변 가능한 경우
    answer: str | None = None


def _format_shop_context(shop_info: dict[str, Any]) -> str:
    lines = ["[가게 정보]"]

    if shop_info.get("business_hour"):
        lines.append(f"- 영업시간: {shop_info['business_hour']}")

    closed = shop_info.get("closed_days")
    if closed is not None:
        day_map = {0: "월요일", 1: "화요일", 2: "수요일", 3: "목요일", 4: "금요일", 5: "토요일", 6: "일요일"}
        lines.append(f"- 정기휴무: {day_map.get(closed, str(closed))}")

    if shop_info.get("services_price"):
        try:
            prices = json.loads(shop_info["services_price"]) if isinstance(shop_info["services_price"], str) else shop_info["services_price"]
            price_text = ", ".join(f"{k} {v:,}원" for k, v in prices.items())
            lines.append(f"- 시술 가격: {price_text}")
        except Exception:
            lines.append(f"- 시술 가격: {shop_info['services_price']}")

    if shop_info.get("service_durations"):
        lines.append(f"- 시술 소요시간: {shop_info['service_durations']}")

    if shop_info.get("deposit_amount"):
        lines.append(f"- 예약금: {shop_info['deposit_amount']:,}원")

    if shop_info.get("account_number"):
        lines.append(f"- 입금 계좌: {shop_info['account_number']}")

    if shop_info.get("policy_text"):
        lines.append(f"- 정책 안내: {shop_info['policy_text']}")

    return "\n".join(lines)


SYSTEM_PROMPT = """당신은 네일샵 챗봇 문의 응답 어시스턴트입니다.
아래 가게 정보를 바탕으로 고객의 입력을 분석하세요.

{shop_context}

다음 세 가지 중 하나로 판단하세요.

[경우 1] 실제 질문 없이 문의 의사만 표현한 경우
예: "기타", "문의요", "궁금한거 있어요", "물어볼게 있어요", "질문 있어요" 등
구체적인 질문 내용이 없고 단순히 문의하고 싶다는 의사 표현만 있는 경우
→ {{"is_trigger": true, "answered": false, "answer": null}}

[경우 2] 구체적인 질문이 있고, 가게 정보로 답변 가능한 경우
→ {{"is_trigger": false, "answered": true, "answer": "한국어로 친절한 답변"}}

[경우 3] 구체적인 질문이 있지만, 가게 정보에 없는 내용인 경우
→ {{"is_trigger": false, "answered": false, "answer": null}}

규칙:
- 가게 정보에 있는 내용만 사용하여 답변하세요. 추측하지 마세요.
- JSON만 출력하세요. 다른 텍스트는 포함하지 마세요."""


class InquiryAgent:
    def __init__(self):
        self._llm = ChatOpenAI(model="gpt-4o", temperature=0)
        self._structured = self._llm.with_structured_output(InquiryResult, method="json_mode")

    def run(self, user_input: str, shop_info: dict[str, Any]) -> InquiryResult:
        shop_context = _format_shop_context(shop_info)
        messages = [
            SystemMessage(content=SYSTEM_PROMPT.format(shop_context=shop_context)),
            HumanMessage(content=user_input),
        ]
        try:
            return self._structured.invoke(messages)
        except Exception:
            return InquiryResult(answered=False, answer=None)
