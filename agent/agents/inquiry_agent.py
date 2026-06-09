from __future__ import annotations

import json
from typing import Any

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

load_dotenv()


class InquiryResult(BaseModel):
    answered: bool
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
아래 가게 정보를 바탕으로 고객의 질문에 친절하게 답변하세요.

{shop_context}

응답 규칙:
- 가게 정보에 있는 내용만 사용하여 답변하세요.
- 가게 정보에 없는 내용은 절대 추측하거나 만들어내지 마세요.
- 답변 가능하면: {{"answered": true, "answer": "한국어로 친절한 답변"}}
- 답변 불가능하면: {{"answered": false, "answer": null}}
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
