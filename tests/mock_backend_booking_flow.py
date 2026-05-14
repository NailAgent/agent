import os
import sys
from pathlib import Path

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
os.environ["USE_MOCK_BACKEND"] = "true"

from agent.agents.schema import BookingSlots
from agent.tools import backend_client as backend_client_module
from agent.tools.backend_client import BackendClient


def force_backend_unavailable() -> None:
    """Force this script to exercise mock fallback rather than a live backend."""

    def _raise_connection_error(*args, **kwargs):
        raise requests.ConnectionError("mock backend flow forces backend unavailable")

    BackendClient.USE_MOCK_BACKEND = True
    backend_client_module.requests.get = _raise_connection_error
    backend_client_module.requests.post = _raise_connection_error


def assert_success(result: dict, label: str) -> None:
    assert result.get("success") is True, f"{label} failed: {result}"


def main() -> None:
    force_backend_unavailable()

    print("1. get_shop_info() mock 테스트")

    shop_info = BackendClient.get_shop_info()
    print(shop_info)

    assert_success(shop_info, "get_shop_info")
    assert shop_info.get("source") == "mock", f"Expected mock source, got: {shop_info.get('source')}"
    assert shop_info.get("deposit_amount") is not None
    assert shop_info.get("business_hour")

    print("\n2. get_schedule() mock 테스트")

    schedule = BackendClient.get_schedule("2026-05-07")
    print(schedule)

    assert_success(schedule, "get_schedule")
    assert schedule.get("source") == "mock", f"Expected mock source, got: {schedule.get('source')}"
    assert schedule.get("business_hours") == {"start": "10:00", "end": "21:00"}
    assert schedule.get("booked_slots") == [
        {"start": "11:00", "end": "12:30", "duration_min": 90},
        {"start": "14:00", "end": "15:00", "duration_min": 60},
    ]

    print("\n3. build_reservation_payload() 테스트")

    slots = BookingSlots(
        name="눈송이",
        phone_num="010-1234-5678",
        reserve_date="2026-05-07",
        reserve_time="17:00",
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

    expected_payload = {
        "name": "눈송이",
        "phone_num": "010-1234-5678",
        "reserve_date": "2026-05-07",
        "reserve_time": "17:00-18:30",
        "estimated_duration_min": 90,
        "service": "젤네일",
        "off_removal": True,
        "deposit_amount": 5000,
        "designer": None,
    }

    for key, expected_value in expected_payload.items():
        assert payload.get(key) == expected_value, (
            f"payload[{key}] expected {expected_value}, got {payload.get(key)}"
        )

    print("\n4. create_reservation() mock 테스트")

    reservation_result = BackendClient.create_reservation(payload)
    print(reservation_result)

    assert_success(reservation_result, "create_reservation")
    assert reservation_result.get("source") == "mock", (
        f"Expected mock source, got: {reservation_result.get('source')}"
    )
    assert reservation_result.get("status_code") == 201

    print("\n✅ mock booking flow 통과")


if __name__ == "__main__":
    main()
