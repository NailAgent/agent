import os
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# shopinfo는 아직 백엔드 미구현이라 mock fallback 허용
# schedule/create_reservation은 실제 backend를 기대
os.environ.setdefault("BACKEND_BASE_URL", "http://localhost:8080")
os.environ["USE_MOCK_BACKEND"] = "true"

from agent.graph.workflow import app
from agent.tools.backend_client import BackendClient


TEST_DATE = os.getenv("TEST_RESERVE_DATE", "2026-05-24")
TEST_TIME = os.getenv("TEST_RESERVE_TIME", "18:30")


def main() -> None:
    BackendClient.DEFAULT_BASE_URL = os.getenv("BACKEND_BASE_URL", "http://localhost:8080").rstrip("/")
    BackendClient.USE_MOCK_BACKEND = True

    suffix = datetime.now().strftime("%H%M%S")

    message = f"""
- *성함: 워크플로우테스트{suffix}
- *전화번호: 010-8888-{suffix[-4:]}
- *젤제거 유무(O/X): O
- *예약 희망 날짜: {TEST_DATE}
- *예약 희망 시간: {TEST_TIME}
- *원하시는 시술 종류: 젤네일
- *과거 방문경험(O/X): X
"""

    initial_state = {
        "user_input": message,
        "history": [],
    }

    print("Backend base URL:", BackendClient.DEFAULT_BASE_URL)
    print("USE_MOCK_BACKEND:", BackendClient.USE_MOCK_BACKEND)
    print("TEST_RESERVE_DATE:", TEST_DATE)
    print("TEST_RESERVE_TIME:", TEST_TIME)
    print("\n[USER]")
    print(message)

    result = app.invoke(initial_state)

    print("\n[RESULT]")
    print("intent:", result.get("intent"))
    print("booking_status:", result.get("booking_status"))
    print("next_action:", result.get("next_action"))
    print("missing_fields:", result.get("missing_fields"))
    print("\n[RESPONSE]")
    print(result.get("response_draft"))
    print("\n[POLICY / BACKEND RESULT]")
    print(result.get("policy_check_results"))

    assert str(result.get("intent")) in {"booking", "IntentType.BOOKING"}, result
    assert result.get("booking_status") == "pending_payment", result
    assert result.get("next_action") == "notify_success", result

    policy = result.get("policy_check_results") or {}
    reservation_result = policy.get("reservation_result") or {}

    assert policy.get("source") == "backend", (
        f"schedule should come from backend, got {policy.get('source')}: {policy}"
    )

    assert reservation_result.get("success") is True, reservation_result
    assert reservation_result.get("source") == "backend", (
        f"create_reservation should use backend, got {reservation_result.get('source')}: {reservation_result}"
    )
    assert reservation_result.get("status_code") in {200, 201}, reservation_result

    print("\n✅ live workflow booking smoke test 통과")


if __name__ == "__main__":
    main()