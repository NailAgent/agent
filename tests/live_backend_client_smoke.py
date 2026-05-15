# ## 실행 코드 - 예약생성 POST까지
# PYTHONPATH=. \
# BACKEND_BASE_URL=http://localhost:8080 \
# USE_MOCK_BACKEND=true \
# RUN_CREATE_RESERVATION=true \
# TEST_RESERVE_DATE=2026-05-20 \
# TEST_RESERVE_TIME=17:00 \
# .venv/bin/python tests/live_backend_client_smoke.py

import os
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# BackendClient가 import될 때 환경변수를 읽는 구조라면,
# import 전에 값을 넣어야 합니다.
DEFAULT_BACKEND_BASE_URL = "http://localhost:8080"
os.environ.setdefault("BACKEND_BASE_URL", DEFAULT_BACKEND_BASE_URL)
os.environ["USE_MOCK_BACKEND"] = "true"    # 목업 데이터 안쓸 경우, False로 변경

from agent.agents.schema import BookingSlots
from agent.tools.backend_client import BackendClient


TEST_DATE = os.getenv("TEST_RESERVE_DATE", "2026-05-20")
TEST_TIME = os.getenv("TEST_RESERVE_TIME", "17:00")
RUN_CREATE_RESERVATION = os.getenv("RUN_CREATE_RESERVATION", "false").lower() in {"1", "true", "yes", "on"}


def assert_backend_success(result: dict, label: str) -> None:
    assert result.get("success") is True, f"{label} failed: {result}"
    assert result.get("source") == "backend", (
        f"{label} expected source='backend', got {result.get('source')}: {result}"
    )


def main() -> None:
    # 혹시 class attribute로 이미 읽혀 있는 경우를 대비
    BackendClient.DEFAULT_BASE_URL = os.getenv("BACKEND_BASE_URL", DEFAULT_BACKEND_BASE_URL).rstrip("/")
    BackendClient.USE_MOCK_BACKEND = True   # 목업 데이터 안쓸 경우, False로 변경

    print("Backend base URL:", BackendClient.DEFAULT_BASE_URL)
    print("USE_MOCK_BACKEND:", BackendClient.USE_MOCK_BACKEND)
    print("TEST_RESERVE_DATE:", TEST_DATE)
    print("TEST_RESERVE_TIME:", TEST_TIME)
    print("RUN_CREATE_RESERVATION:", RUN_CREATE_RESERVATION)

    print("\n1. GET /api/v1/shopinfo 테스트")
    shop_info = BackendClient.get_shop_info()
    print(shop_info)

    assert shop_info.get("success") is True, f"get_shop_info failed: {shop_info}"
    assert shop_info.get("source") == "mock", (
        f"shopinfo is currently not implemented in backend, expected source='mock', got {shop_info.get('source')}: {shop_info}"
    )
    assert shop_info.get("business_hour"), "business_hour is missing"
    assert shop_info.get("deposit_amount") is not None, "deposit_amount is missing"
    assert shop_info.get("booking_form_text"), "booking_form_text is missing"

    print("\n2. GET /api/v1/bookings/schedule 테스트")
    schedule = BackendClient.get_schedule(TEST_DATE)
    print(schedule)

    assert_backend_success(schedule, "get_schedule")
    assert schedule.get("business_hours"), "business_hours is missing"
    assert isinstance(schedule.get("booked_slots"), list), "booked_slots must be list"

    print("\n3. build_reservation_payload() 테스트")

    now_suffix = datetime.now().strftime("%H%M")

    slots = BookingSlots(
        name=f"테스트예약{now_suffix}",
        phone_num=f"010-9999-{now_suffix}",
        reserve_date=TEST_DATE,
        reserve_time=TEST_TIME,
        service_code="GEL_NAIL",
        off_removal=True,
        past_visit=False,
    )

    payload = BackendClient.build_reservation_payload(
        slots=slots,
        estimated_duration_min=90,
        deposit_amount=shop_info["deposit_amount"],
        designer=None,
    )

    print(payload)

    required_payload_fields = [
        "name",
        "phone_num",
        "reserve_date",
        "reserve_time",
        "estimated_duration_min",
        "service",
        "off_removal",
        "deposit_amount",
    ]

    missing = [
        field
        for field in required_payload_fields
        if payload.get(field) is None or payload.get(field) == ""
    ]

    assert not missing, f"Reservation payload missing required fields: {missing}"
    assert payload["reserve_time"].count("-") == 1, (
        f"reserve_time must be range format, got {payload['reserve_time']}"
    )

    print("\n4. POST /api/v1/bookings 테스트")

    if not RUN_CREATE_RESERVATION:
        print("실제 예약 생성 POST는 건너뜁니다.")
        print("실제 DB 저장까지 테스트하려면 RUN_CREATE_RESERVATION=true로 실행하세요.")
        print("반복 POST 테스트 시 TEST_RESERVE_DATE 또는 TEST_RESERVE_TIME을 바꿔 충돌을 피하세요.")
        print("\n✅ backend_client live read/payload smoke test 통과")
        return

    print("주의: 실제 예약 생성 POST를 실행합니다.")
    print("반복 실행 시 같은 날짜/시간 예약 충돌이 날 수 있습니다.")

    reservation_result = BackendClient.create_reservation(payload)
    print(reservation_result)

    assert_backend_success(reservation_result, "create_reservation")
    assert reservation_result.get("status_code") in {200, 201}, (
        f"Unexpected status_code: {reservation_result}"
    )

    print("\n✅ backend_client live full booking smoke test 통과")


if __name__ == "__main__":
    main()
