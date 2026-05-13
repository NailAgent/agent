from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
import sys

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

from agent.graph.workflow import app

STRICT_ASSERT = False

@dataclass
class TestCase:
    name: str
    message: str
    expected_intent: Optional[str] = None
    expected_not_intent: Optional[str] = None
    expected_status: Optional[str] = None
    expected_missing_fields: list[str] = field(default_factory=list)
    expected_response_contains: list[str] = field(default_factory=list)


def to_str(value: Any) -> str:
    """Normalize Enum or None values to plain string."""
    if value is None:
        return ""
    return value.value if hasattr(value, "value") else str(value)


def format_slots(slots: Any) -> dict:
    """Convert Pydantic slots object to dict for readable output."""
    if slots is None:
        return {}

    if hasattr(slots, "model_dump"):
        return slots.model_dump()

    if hasattr(slots, "dict"):
        return slots.dict()

    return dict(slots) if isinstance(slots, dict) else {"raw": slots}


def run_graph(message: str) -> dict:
    """Run one message through the LangGraph workflow."""
    initial_state = {
        "user_input": message,
        "history": [],
    }

    return app.invoke(initial_state)


def check_case(case: TestCase, result: dict) -> tuple[bool, list[str]]:
    """Check test result and return pass/fail with failure reasons."""
    failures = []

    intent = to_str(result.get("intent"))
    status = to_str(result.get("booking_status"))
    missing_fields = result.get("missing_fields") or []
    response = result.get("response_draft") or ""

    if case.expected_intent and intent != case.expected_intent:
        failures.append(
            f"expected intent={case.expected_intent}, got intent={intent}"
        )

    if case.expected_not_intent and intent == case.expected_not_intent:
        failures.append(
            f"expected intent != {case.expected_not_intent}, got intent={intent}"
        )

    if case.expected_status and status != case.expected_status:
        failures.append(
            f"expected booking_status={case.expected_status}, got booking_status={status}"
        )

    for field_name in case.expected_missing_fields:
        if field_name not in missing_fields:
            failures.append(
                f"expected missing field '{field_name}', got missing_fields={missing_fields}"
            )

    for text in case.expected_response_contains:
        if text not in response:
            failures.append(
                f"expected response to contain '{text}'"
            )

    return len(failures) == 0, failures


def print_result(case: TestCase, result: dict, passed: bool, failures: list[str]) -> None:
    """Print readable test result."""
    intent = to_str(result.get("intent"))
    status = to_str(result.get("booking_status"))
    missing_fields = result.get("missing_fields") or []
    response = result.get("response_draft") or ""
    slots = format_slots(result.get("slots"))

    print("\n" + "=" * 80)
    print(f"[TEST] {case.name}")
    print("=" * 80)
    print("[USER]")
    print(case.message.strip())
    print("\n[RESULT]")
    print(f"- PASS: {passed}")
    print(f"- intent: {intent}")
    print(f"- booking_status: {status}")
    print(f"- missing_fields: {missing_fields}")
    print(f"- slots: {slots}")
    print("\n[RESPONSE]")
    print(response)

    if failures:
        print("\n[FAILURES]")
        for failure in failures:
            print(f"- {failure}")


def run_case(case: TestCase) -> bool:
    """Run and check one test case."""
    result = run_graph(case.message)
    passed, failures = check_case(case, result)
    print_result(case, result, passed, failures)

    if STRICT_ASSERT and not passed:
        raise AssertionError(f"{case.name} failed: {failures}")

    return passed


def main() -> None:
    cases = [
        TestCase(
            name="1. 예약 문의 → booking으로 분류되는지",
            message="예약 문의",
            expected_intent="booking",
        ),
        TestCase(
            name="2. 예약만 말하고 정보 없음 → 예약 양식 안내",
            message="예약하고 싶어요",
            expected_intent="booking",
            expected_response_contains=[
                "예약 문의 주셔서 감사합니다",
                "예약 형식",
                "성함",
                "전화번호",
            ],
        ),
        TestCase(
            name="3. 이름 누락 → 이름만 추가 질문",
            message="""
            - *전화번호: 010-1234-5678
            - *젤제거 유무: O
            - *예약 희망 날짜: 2026-05-07
            - *예약 희망 시간: 17:00
            - *원하시는 시술 종류: 젤네일
            - *과거 방문경험: X
            """,
            expected_intent="booking",
            expected_missing_fields=["name"],
            expected_response_contains=["성함"],
        ),
        TestCase(
            name="4. 월요일 예약 → rejected",
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
            expected_response_contains=["월요일"],
        ),
        TestCase(
            name="5-1. 영업시간 전 예약 → rejected",
            message="""
            - *성함: 김민지
            - *전화번호: 010-1111-2222
            - *젤제거 유무: X
            - *예약 희망 날짜: 2026-05-07
            - *예약 희망 시간: 09:00
            - *원하시는 시술 종류: 젤네일
            - *과거 방문경험: X
            """,
            expected_intent="booking",
            expected_status="rejected",
        ),
        TestCase(
            name="5-2. 영업시간 후 예약 → rejected",
            message="""
            - *성함: 김민지
            - *전화번호: 010-1111-2222
            - *젤제거 유무: X
            - *예약 희망 날짜: 2026-05-07
            - *예약 희망 시간: 22:30
            - *원하시는 시술 종류: 젤네일
            - *과거 방문경험: X
            """,
            expected_intent="booking",
            expected_status="rejected",
        ),
        TestCase(
            name="6. 기존 예약과 충돌 → rejected + 대체 시간 추천",
            message="""
            - *성함: 박서연
            - *전화번호: 010-3333-4444
            - *젤제거 유무: X
            - *예약 희망 날짜: 2026-05-07
            - *예약 희망 시간: 14:00
            - *원하시는 시술 종류: 젤네일
            - *과거 방문경험: X
            """,
            expected_intent="booking",
            expected_status="rejected",
            expected_response_contains=["예약 가능한 시간대"],
        ),
        TestCase(
            name="7. 제거 O일 때 duration +30 되는지",
            message="""
            - *성함: 김지수
            - *전화번호: 010-1234-5678
            - *젤제거 유무: O
            - *예약 희망 날짜: 2026-05-07
            - *예약 희망 시간: 17:00
            - *원하시는 시술 종류: 젤네일
            - *과거 방문경험: X
            """,
            expected_intent="booking",
            expected_status="pending_payment",
            expected_response_contains=["90분"],
        ),
        TestCase(
            name="8-1. 예약 변경 → v1 미지원 안내",
            message="예약 시간 바꾸고 싶어요",
            expected_intent="change",
            expected_response_contains=["예약 변경", "준비 중"],
        ),
        TestCase(
            name="8-2. 예약 취소 → v1 미지원 안내",
            message="예약 취소하고 싶어요",
            expected_intent="cancel",
            expected_response_contains=["예약 취소", "준비 중"],
        ),
        TestCase(
            name="9-1. 가격 문의 → booking으로 가지 않는지",
            message="가격 얼마예요?",
            expected_intent="inquiry",
            expected_not_intent="booking",
            expected_response_contains=["문의 감사합니다"],
        ),
        TestCase(
            name="9-2. 영업시간 문의 → booking으로 가지 않는지",
            message="영업시간이 어떻게 되나요?",
            expected_intent="inquiry",
            expected_not_intent="booking",
            expected_response_contains=["문의 감사합니다"],
        ),
    ]

    # 테스트 실패한 케이스만 재실험
    # FAILED_CASE_NAMES = {
    #     "8-1. 예약 변경 → v1 미지원 안내",
    #     "8-2. 예약 취소 → v1 미지원 안내",
    #     "9-1. 가격 문의 → booking으로 가지 않는지",
    #     "9-2. 영업시간 문의 → booking으로 가지 않는지",
    # }

    # cases = [
    #     case for case in cases
    #     if case.name in FAILED_CASE_NAMES
    # ]

    total = len(cases)
    passed_count = 0

    for case in cases:
        if run_case(case):
            passed_count += 1

    print("\n" + "#" * 80)
    print(f"[SUMMARY] {passed_count}/{total} passed")
    print("#" * 80)

    if STRICT_ASSERT and passed_count != total:
        raise AssertionError(f"{total - passed_count} test(s) failed")


if __name__ == "__main__":
    main()
