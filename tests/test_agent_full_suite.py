from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("BACKEND_BASE_URL", "http://localhost:8080")
os.environ["USE_MOCK_BACKEND"] = "true"
load_dotenv(PROJECT_ROOT / ".env")

from agent.agents.schema import BookingSlots
from agent.graph.workflow import app
from agent.tools.backend_client import BackendClient


STRICT_ASSERT = True
SAMPLE_KAKAO_USER_ID = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
SAMPLE_PLUSFRIEND_USER_KEY = "ABCDef1234ab"


@dataclass
class Case:
    name: str
    message: str
    expected_intent: Optional[str] = None
    expected_status: Optional[str] = None
    expected_next_action: Optional[str] = None
    expected_response_contains: list[str] = field(default_factory=list)
    expected_slot_values: dict[str, Any] = field(default_factory=dict)
    initial_state: dict[str, Any] = field(default_factory=dict)


def to_plain(value: Any) -> str:
    if value is None:
        return ""
    return value.value if hasattr(value, "value") else str(value)


def dump_slots(slots: Any) -> dict:
    if slots is None:
        return {}
    if hasattr(slots, "model_dump"):
        return slots.model_dump()
    if hasattr(slots, "dict"):
        return slots.dict()
    return dict(slots) if isinstance(slots, dict) else {"raw": slots}


def run_graph(message: str, extra_state: Optional[dict[str, Any]] = None, thread_id: str = "test") -> dict:
    state = {
        "user_input": message,
        "history": [],
    }
    if extra_state:
        state.update(extra_state)
    return app.invoke(state, config={"configurable": {"thread_id": thread_id}})


def assert_contains(haystack: str, needles: list[str], context: str) -> list[str]:
    failures = []
    for needle in needles:
        if needle not in haystack:
            failures.append(f"{context} expected to contain '{needle}'")
    return failures


def check_case(case: Case, result: dict) -> tuple[bool, list[str]]:
    failures: list[str] = []
    intent = to_plain(result.get("intent"))
    status = to_plain(result.get("booking_status"))
    next_action = to_plain(result.get("next_action"))
    response = result.get("response_draft") or ""
    slots = dump_slots(result.get("slots"))

    if case.expected_intent and intent != case.expected_intent:
        failures.append(f"expected intent={case.expected_intent}, got {intent}")
    if case.expected_status and status != case.expected_status:
        failures.append(f"expected booking_status={case.expected_status}, got {status}")
    if case.expected_next_action and next_action != case.expected_next_action:
        failures.append(f"expected next_action={case.expected_next_action}, got {next_action}")

    failures.extend(assert_contains(response, case.expected_response_contains, "response"))

    for key, expected in case.expected_slot_values.items():
        if slots.get(key) != expected:
            failures.append(f"expected slots['{key}']={expected}, got {slots.get(key)}")

    return len(failures) == 0, failures


def print_result(case: Case, result: dict, passed: bool, failures: list[str]) -> None:
    print("\n" + "=" * 88)
    print(f"[TEST] {case.name}")
    print("=" * 88)
    print("[USER]")
    print(case.message.strip())
    print("\n[RESULT]")
    print(f"- PASS: {passed}")
    print(f"- intent: {to_plain(result.get('intent'))}")
    print(f"- booking_status: {to_plain(result.get('booking_status'))}")
    print(f"- next_action: {to_plain(result.get('next_action'))}")
    print(f"- missing_fields: {result.get('missing_fields') or []}")
    print(f"- slots: {dump_slots(result.get('slots'))}")
    print("\n[RESPONSE]")
    print(result.get("response_draft") or "")
    if failures:
        print("\n[FAILURES]")
        for failure in failures:
            print(f"- {failure}")


def run_case(case: Case) -> bool:
    result = run_graph(case.message, case.initial_state, thread_id=case.name)
    passed, failures = check_case(case, result)
    print_result(case, result, passed, failures)

    if STRICT_ASSERT and not passed:
        raise AssertionError(f"{case.name} failed: {failures}")
    return passed


def backend_smoke() -> None:
    print("\n" + "#" * 88)
    print("[BACKEND CLIENT SMOKE]")
    print("#" * 88)

    shop_info = BackendClient.get_shop_info()
    print("shop_info:", shop_info)
    assert shop_info.get("success") is True, shop_info
    assert shop_info.get("business_hour"), shop_info
    assert shop_info.get("services_price"), shop_info
    assert shop_info.get("service_durations"), shop_info

    schedule = BackendClient.get_schedule("2026-05-07")
    print("schedule:", schedule)
    assert schedule.get("success") is True, schedule
    assert schedule.get("business_hours"), schedule
    assert isinstance(schedule.get("booked_slots"), list), schedule

    lookup = BackendClient.lookup_kakao_customer(SAMPLE_KAKAO_USER_ID, SAMPLE_PLUSFRIEND_USER_KEY)
    print("kakao_lookup:", lookup)
    assert lookup.get("success") is True, lookup
    assert lookup.get("is_existing") is True, lookup
    assert lookup.get("name") == "정교은", lookup
    assert lookup.get("phone_num") == "010-1111-2222", lookup

    slots = BookingSlots(
        name="테스트고객",
        phone_num="010-9999-0000",
        reserve_date="2026-05-20",
        reserve_time="16:00",
        service_code="GEL_NAIL",
        off_removal=True,
        past_visit=False,
    )
    payload = BackendClient.build_reservation_payload(
        slots=slots,
        estimated_duration_min=90,
        deposit_amount=shop_info["deposit_amount"],
        designer="사장님",
        kakao_user_id=SAMPLE_KAKAO_USER_ID,
        plusfriend_user_key=SAMPLE_PLUSFRIEND_USER_KEY,
    )
    print("payload:", payload)
    assert payload["kakao_user_id"] == SAMPLE_KAKAO_USER_ID, payload
    assert payload["plusfriend_user_key"] == SAMPLE_PLUSFRIEND_USER_KEY, payload
    assert payload["reserve_time"] == "16:00-17:30", payload

    reservation_result = BackendClient.create_reservation(payload)
    print("create_reservation:", reservation_result)
    assert reservation_result.get("success") is True, reservation_result
    assert reservation_result.get("source") == "mock", reservation_result


def main() -> None:
    BackendClient.DEFAULT_BASE_URL = os.getenv("BACKEND_BASE_URL", "http://localhost:8080").rstrip("/")
    BackendClient.USE_MOCK_BACKEND = True

    backend_smoke()

    cases = [
        Case(
            name="1. greeting",
            message="안녕하세요",
            expected_intent="greeting",
            expected_status="N/A",
            expected_next_action="respond_only",
            expected_response_contains=["예약문의를 원하시면", "예약취소"],
        ),
        Case(
            name="2. booking guide",
            message="예약하고 싶어요",
            expected_intent="booking",
            expected_status="N/A",
            expected_next_action="ask_followup",
            expected_response_contains=["예약 문의 주셔서 감사합니다", "성함", "전화번호"],
        ),
        Case(
            name="3. booking missing name",
            message="""
            - *전화번호: 010-1234-5678
            - *젤제거 유무: O
            - *예약 희망 날짜: 2026-05-20
            - *예약 희망 시간: 17:00
            - *원하시는 시술 종류: 젤네일
            - *과거 방문경험: X
            """,
            expected_intent="booking",
            expected_status="N/A",
            expected_next_action="ask_followup",
            expected_response_contains=["성함을 알려주세요"],
        ),
        Case(
            name="4. booking with kakao identity",
            message="""
            - *젤제거 유무: O
            - *예약 희망 날짜: 2026-05-20
            - *예약 희망 시간: 16:00
            - *원하시는 시술 종류: 젤네일
            - *과거 방문경험: X
            """,
            expected_intent="booking",
            expected_status="pending_payment",
            expected_next_action="notify_success",
            expected_response_contains=["예약이 가능합니다", "예약 정보가 임시 저장되었습니다", "입금 안내"],
            expected_slot_values={"name": "정교은", "phone_num": "010-1111-2222"},
            initial_state={
                "kakao_user_id": SAMPLE_KAKAO_USER_ID,
                "plusfriend_user_key": SAMPLE_PLUSFRIEND_USER_KEY,
            },
        ),
        Case(
            name="5. monday booking rejected",
            message="""
            - *성함: 이민호
            - *전화번호: 010-9999-8888
            - *젤제거 유무: X
            - *예약 희망 날짜: 2024-05-06
            - *예약 희망 시간: 14:00
            - *원하시는 시술 종류: 젤네일
            - *과거 방문경험: O
            """,
            expected_intent="booking",
            expected_status="rejected",
            expected_next_action="notify_failure",
            expected_response_contains=["월요일", "예약 가능한 시간대"],
        ),
        Case(
            name="6. booking pending payment",
            message="""
            - *성함: 김지수
            - *전화번호: 010-1234-5678
            - *젤제거 유무: O
            - *예약 희망 날짜: 2026-05-20
            - *예약 희망 시간: 17:00
            - *원하시는 시술 종류: 젤네일
            - *과거 방문경험: X
            """,
            expected_intent="booking",
            expected_status="pending_payment",
            expected_next_action="notify_success",
            expected_response_contains=["17:00-18:30", "예약금"],
        ),
        Case(
            name="7. change follow-up",
            message="예약 시간 바꾸고 싶어요",
            expected_intent="change",
            expected_status="N/A",
            expected_next_action="ask_followup",
            expected_response_contains=["성함"],
        ),
        Case(
            name="8. change pending_review",
            message="남민서 2026-05-13 14:00 아트네일 예약 변경하고 싶어요",
            expected_intent="change",
            expected_status="pending_review",
            expected_next_action="ask_followup",
            expected_response_contains=["기존 예약을 찾았습니다", "남민서", "변경 희망 일정"],
        ),
        Case(
            name="9. change actual update",
            message="남민서 2026-05-13 14:00 2026-05-15 16:00 아트네일 예약 변경하고 싶어요",
            expected_intent="change",
            expected_status="updated",
            expected_next_action="notify_success",
            expected_response_contains=["기존 예약이 변경되었습니다", "예약자: 남민서", "2026-05-15 16:00-17:30"],
        ),
        Case(
            name="10. cancel follow-up",
            message="예약 취소하고 싶어요",
            expected_intent="cancel",
            expected_status="N/A",
            expected_next_action="ask_followup",
            expected_response_contains=["예약 취소 문의 감사합니다", "예약 날짜/시간"],
        ),
        Case(
            name="11. cancel actual",
            message="김지수 2026-05-14 13:00 페디큐어 예약 취소하고 싶어요",
            expected_intent="cancel",
            expected_status="cancelled",
            expected_next_action="notify_success",
            expected_response_contains=["예약이 취소되었습니다", "예약자: 김지수"],
        ),
        Case(
            name="12. payment follow-up",
            message="정교은 2026-05-13 11:00 젤네일 입금했어요",
            expected_intent="payment",
            expected_status="pending_payment",
            expected_next_action="notify_failure",
            expected_response_contains=["아직 결제가 확인되지 않았습니다"],
        ),
        Case(
            name="13. payment confirm",
            message="정교은 입금 확인해주세요",
            expected_intent="payment",
            expected_status="pending_payment",
            expected_next_action="notify_failure",
            expected_response_contains=["아직 결제가 확인되지 않았습니다"],
        ),
        Case(
            name="14. payment refund",
            message="정교은 입금 됐나요?",
            expected_intent="payment",
            expected_status="pending_payment",
            expected_next_action="notify_failure",
            expected_response_contains=["아직 결제가 확인되지 않았습니다"],
        ),
        Case(
            name="15. inquiry",
            message="가격 얼마예요?",
            expected_intent="inquiry",
            expected_status="N/A",
            expected_next_action="respond_only",
            expected_response_contains=["문의 감사합니다"],
        ),
        Case(
            name="16. unknown routing",
            message="이거 뭐죠?",
            expected_intent="unknown",
            expected_status="N/A",
            expected_next_action="respond_only",
            expected_response_contains=["예약 문의", "예약 변경", "예약 취소"],
        ),
    ]

    passed = 0
    for case in cases:
        if run_case(case):
            passed += 1

    print("\n" + "#" * 88)
    print(f"[SUMMARY] {passed}/{len(cases)} passed")
    print("#" * 88)

    if STRICT_ASSERT and passed != len(cases):
        raise AssertionError(f"{len(cases) - passed} test(s) failed")


if __name__ == "__main__":
    main()
