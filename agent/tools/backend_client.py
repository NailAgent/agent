from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Optional

import requests

from agent.agents.schema import BookingSlots
from agent.tools.backend_errors import (
    customer_error,
    reservation_error,
    reservation_list_error,
    schedule_error,
    shop_info_error,
)
from agent.tools.backend_normalizers import (
    format_reserve_time,
    normalize_kakao_customer,
    normalize_reservation_list,
    normalize_schedule,
    normalize_shop_info,
)
from agent.tools.mock_loader import load_mock_json


class BackendClient:
    """Thin adapter for backend API calls and mock fallback routing."""

    DEFAULT_BASE_URL = os.getenv("BACKEND_BASE_URL", "http://localhost:8080").rstrip("/")
    USE_MOCK_BACKEND = os.getenv("USE_MOCK_BACKEND", "false").lower() in {"1", "true", "yes", "on"}

    @classmethod
    def get_shop_info(cls) -> dict[str, Any]:
        try:
            response = requests.get(f"{cls.DEFAULT_BASE_URL}/api/v1/shopinfo", timeout=5)
            payload = cls._response_json(response)

            if response.status_code == 200:
                return normalize_shop_info(payload, source="backend", status_code=response.status_code)

            mock = cls._load_mock("shopinfo_200.json")
            if mock:
                return normalize_shop_info(mock, source="mock", status_code=mock.get("status", 200))

            return shop_info_error(
                status_code=response.status_code,
                error_code=payload.get("error_code", "UNKNOWN_BACKEND_ERROR"),
                message=payload.get("message", "샵 정보를 불러올 수 없습니다."),
                next_action="retry_or_human_review" if response.status_code >= 500 else "human_review",
            )
        except (requests.RequestException, ValueError) as exc:
            mock = cls._load_mock("shopinfo_200.json")
            if mock:
                return normalize_shop_info(mock, source="mock", status_code=mock.get("status", 200))

            return shop_info_error(
                error_code="BACKEND_UNAVAILABLE",
                message="백엔드 서버에 연결할 수 없습니다.",
                error=str(exc),
                next_action="retry_or_human_review",
            )

    @classmethod
    def get_schedule(cls, date_str: str) -> dict[str, Any]:
        if not cls._is_valid_date(date_str):
            return schedule_error(
                date_str,
                status_code=400,
                error_code="INVALID_DATE_PARAMETER",
                message="date는 YYYY-MM-DD 형식이어야 합니다.",
                next_action="human_review",
            )

        try:
            response = requests.get(
                f"{cls.DEFAULT_BASE_URL}/api/v1/bookings/schedule",
                params={"date": date_str},
                timeout=5,
            )
            payload = cls._response_json(response)

            if response.status_code == 200:
                return normalize_schedule(payload, source="backend", status_code=response.status_code, date_str=date_str)

            mock = cls._load_mock("schedule_200.json")
            if mock:
                return normalize_schedule(mock, source="mock", status_code=mock.get("status", 200), date_str=date_str)

            return schedule_error(
                date_str,
                status_code=response.status_code,
                error_code=payload.get("error_code", "UNKNOWN_BACKEND_ERROR"),
                message=payload.get("message", "예약 스케줄을 불러올 수 없습니다."),
                next_action="retry_or_human_review" if response.status_code >= 500 else "human_review",
            )
        except (requests.RequestException, ValueError) as exc:
            if cls.USE_MOCK_BACKEND:
                mock = cls._load_mock("schedule_200.json")
                if mock:
                    return normalize_schedule(mock, source="mock", status_code=mock.get("status", 200), date_str=date_str)

            return schedule_error(
                date_str,
                error_code="BACKEND_UNAVAILABLE",
                message=(
                    "백엔드 연결 실패 후 사용할 mock schedule도 없습니다."
                    if cls.USE_MOCK_BACKEND
                    else "백엔드 서버에 연결할 수 없습니다."
                ),
                error=str(exc),
                next_action="retry_or_human_review",
            )

    @classmethod
    def create_reservation(cls, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = requests.post(
                f"{cls.DEFAULT_BASE_URL}/api/v1/bookings",
                json=payload,
                timeout=5,
            )
            response_payload = cls._response_json(response)

            if 200 <= response.status_code < 300:
                return {
                    "success": True,
                    "source": "backend",
                    "status_code": response.status_code,
                    "response": response_payload or None,
                }

            return reservation_error(
                status_code=response.status_code,
                error_code=response_payload.get("error_code", "UNKNOWN_BACKEND_ERROR"),
                message=response_payload.get("message", "예약 생성에 실패했습니다."),
                response=response_payload or None,
                next_action="retry_or_human_review" if response.status_code >= 500 else "human_review",
            )
        except (requests.RequestException, ValueError) as exc:
            if cls.USE_MOCK_BACKEND:
                mock = cls._load_mock("create_booking_201.json")
                if mock:
                    return {
                        "success": True,
                        "source": "mock",
                        "status_code": mock.get("status", 201),
                        "response": mock,
                    }

            return reservation_error(
                error_code="BACKEND_UNAVAILABLE",
                message=(
                    "백엔드 연결 실패 후 사용할 mock 예약 생성 응답도 없습니다."
                    if cls.USE_MOCK_BACKEND
                    else "백엔드 서버에 연결할 수 없습니다."
                ),
                error=str(exc),
                next_action="retry_or_human_review",
            )

    @classmethod
    def list_reservations(cls, page: int = 1, size: int = 100) -> dict[str, Any]:
        try:
            response = requests.get(
                f"{cls.DEFAULT_BASE_URL}/api/v1/bookings",
                params={"page": page, "size": size},
                timeout=5,
            )
            payload = cls._response_json(response)

            if response.status_code == 200:
                return normalize_reservation_list(payload, source="backend", status_code=response.status_code, page=page)

            return reservation_list_error(
                page=page,
                status_code=response.status_code,
                error_code=payload.get("error_code", "UNKNOWN_BACKEND_ERROR"),
                message=payload.get("message", "예약 목록을 불러올 수 없습니다."),
                response=payload or None,
                next_action="retry_or_human_review" if response.status_code >= 500 else "human_review",
            )
        except (requests.RequestException, ValueError) as exc:
            if cls.USE_MOCK_BACKEND:
                mock = cls._load_mock("bookings_200.json")
                if mock:
                    return normalize_reservation_list(mock, source="mock", status_code=mock.get("status", 200), page=page)

            return reservation_list_error(
                page=page,
                error_code="BACKEND_UNAVAILABLE",
                message=(
                    "백엔드 연결 실패 후 사용할 mock 예약 목록도 없습니다."
                    if cls.USE_MOCK_BACKEND
                    else "백엔드 서버에 연결할 수 없습니다."
                ),
                error=str(exc),
                next_action="retry_or_human_review",
            )

    @classmethod
    @classmethod
    def lookup_kakao_customer(
        cls,
        kakao_user_id: str,
        plusfriend_user_key: Optional[str] = None,
    ) -> dict[str, Any]:
        if not kakao_user_id:
            return customer_error(
                error_code="INVALID_KAKAO_USER_ID",
                message="카카오 유저 ID가 필요합니다.",
                next_action="human_review",
            )

        payload = {"kakao_user_id": kakao_user_id}
        if plusfriend_user_key:
            payload["plusfriend_user_key"] = plusfriend_user_key

        try:
            response = requests.post(
                f"{cls.DEFAULT_BASE_URL}/api/v1/kakao-customers",
                json=payload,
                timeout=5,
            )
            response_payload = cls._response_json(response)

            if response.status_code == 200:
                return normalize_kakao_customer(response_payload, source="backend", status_code=response.status_code)

            if cls.USE_MOCK_BACKEND:
                mock = cls._load_mock("kakao_customer_200.json")
                if mock:
                    return normalize_kakao_customer(mock, source="mock", status_code=mock.get("status", 200))

            return customer_error(
                status_code=response.status_code,
                error_code=response_payload.get("error_code", "UNKNOWN_BACKEND_ERROR"),
                message=response_payload.get("message", "카카오 고객 정보를 불러올 수 없습니다."),
                response=response_payload or None,
                next_action="retry_or_human_review" if response.status_code >= 500 else "human_review",
            )
        except (requests.RequestException, ValueError) as exc:
            if cls.USE_MOCK_BACKEND:
                mock = cls._load_mock("kakao_customer_200.json")
                if mock:
                    return normalize_kakao_customer(mock, source="mock", status_code=mock.get("status", 200))
                return {
                    "success": True,
                    "source": "mock",
                    "status_code": 200,
                    "is_existing": False,
                    "kakao_user_id": kakao_user_id,
                    "plusfriend_user_key": plusfriend_user_key,
                    "name": None,
                    "phone_num": None,
                }

            return customer_error(
                error_code="BACKEND_UNAVAILABLE",
                message="백엔드 서버에 연결할 수 없습니다.",
                error=str(exc),
                next_action="retry_or_human_review",
            )

    def find_reservations(
        cls,
        name: Optional[str] = None,
        phone_num: Optional[str] = None,
        reserve_date: Optional[str] = None,
        reserve_time: Optional[str] = None,
        service: Optional[str] = None,
        visit_status: Optional[str] = None,
        payment_status: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        page = 1
        max_pages = 10

        while page <= max_pages:
            snapshot = cls.list_reservations(page=page, size=100)
            bookings = snapshot.get("bookings", [])
            if not bookings:
                break
            candidates.extend(bookings)
            if not snapshot.get("success", True) or snapshot.get("source") == "mock":
                break
            total_pages = snapshot.get("total_pages", 1)
            if page >= total_pages:
                break
            page += 1

        def _matches(item: dict[str, Any]) -> bool:
            if name and name not in str(item.get("name", "")):
                return False
            if phone_num and phone_num not in str(item.get("phone_num", "")):
                return False
            if reserve_date and reserve_date != str(item.get("reserve_date", "")):
                return False
            if reserve_time:
                item_time = str(item.get("reserve_time", ""))
                if reserve_time not in item_time and item_time not in reserve_time:
                    return False
            if service and service not in str(item.get("service", "")):
                return False
            actual_visit_status = str(item.get("visit_status", "")).strip()
            if visit_status and actual_visit_status and visit_status.upper() != actual_visit_status.upper():
                return False
            actual_payment_status = str(item.get("payment_status", "")).strip()
            if payment_status and actual_payment_status and payment_status.upper() != actual_payment_status.upper():
                return False
            return True

        return [item for item in candidates if _matches(item)]

    @classmethod
    def format_reservation_summary(cls, reservation: dict[str, Any]) -> str:
        return (
            f"[예약 #{reservation.get('id', '?')}] "
            f"{reservation.get('name', '알 수 없음')} | "
            f"{reservation.get('reserve_date', '날짜 미상')} | "
            f"{reservation.get('reserve_time', '시간 미상')} | "
            f"{reservation.get('service', '시술 미상')} | "
            f"{reservation.get('visit_status', '상태 미상')} | "
            f"{reservation.get('payment_status', '결제 상태 미상')}"
        )

    @classmethod
    def build_reservation_payload(
        cls,
        slots: BookingSlots,
        estimated_duration_min: int,
        deposit_amount: Optional[int] = None,
        designer: Optional[str] = None,
        kakao_user_id: Optional[str] = None,
        plusfriend_user_key: Optional[str] = None,
    ) -> dict[str, Any]:
        shop = cls.get_shop_info() if deposit_amount is None else {}
        resolved_deposit_amount = deposit_amount if deposit_amount is not None else shop.get("deposit_amount")

        missing_fields = []
        for field_name in ("name", "phone_num", "reserve_date", "reserve_time"):
            if cls._is_blank(getattr(slots, field_name, None)):
                missing_fields.append(field_name)
        if cls._is_blank(slots.service_code):
            missing_fields.append("service")
        if slots.off_removal is None:
            missing_fields.append("off_removal")
        if estimated_duration_min is None:
            missing_fields.append("estimated_duration_min")
        if resolved_deposit_amount is None:
            missing_fields.append("deposit_amount")
        if missing_fields:
            raise ValueError(f"Missing required reservation fields: {', '.join(missing_fields)}")

        service_map = {
            "GEL_BASIC": "기본네일",
            "GEL_NAIL": "젤네일",
            "PEDICURE": "페디큐어",
        }
        payload = {
            "name": slots.name,
            "phone_num": slots.phone_num,
            "reserve_date": slots.reserve_date,
            "reserve_time": format_reserve_time(slots.reserve_time, estimated_duration_min),
            "estimated_duration_min": estimated_duration_min,
            "service": service_map.get(slots.service_code or "", slots.service_code or "젤네일"),
            "off_removal": bool(slots.off_removal),
            "deposit_amount": resolved_deposit_amount,
            "designer": designer,
            "kakao_user_id": kakao_user_id,
            "plusfriend_user_key": plusfriend_user_key,
        }

        missing_payload_fields = [
            field_name
            for field_name in (
                "name",
                "phone_num",
                "reserve_date",
                "reserve_time",
                "estimated_duration_min",
                "service",
                "off_removal",
                "deposit_amount",
            )
            if cls._is_blank(payload.get(field_name))
        ]
        if missing_payload_fields:
            raise ValueError(f"Missing required reservation fields: {', '.join(missing_payload_fields)}")

        return payload

    @classmethod
    def update_reservation(cls, reservation_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = requests.patch(
                f"{cls.DEFAULT_BASE_URL}/api/v1/bookings/{reservation_id}",
                json=payload,
                timeout=5,
            )
            response_payload = cls._response_json(response)

            if 200 <= response.status_code < 300:
                return {
                    "success": True,
                    "source": "backend",
                    "status_code": response.status_code,
                    "response": response_payload or None,
                }

            return reservation_error(
                status_code=response.status_code,
                error_code=response_payload.get("error_code", "UNKNOWN_BACKEND_ERROR"),
                message=response_payload.get("message", "예약 수정에 실패했습니다."),
                response=response_payload or None,
                next_action="retry_or_human_review" if response.status_code >= 500 else "human_review",
            )
        except (requests.RequestException, ValueError) as exc:
            if cls.USE_MOCK_BACKEND:
                return {
                    "success": True,
                    "source": "mock",
                    "status_code": 200,
                    "response": {
                        "reservation_id": reservation_id,
                        "updated_fields": payload,
                    },
                }

            return reservation_error(
                error_code="BACKEND_UNAVAILABLE",
                message="백엔드 서버에 연결할 수 없습니다.",
                error=str(exc),
                next_action="retry_or_human_review",
            )

    @classmethod
    def delete_reservation(cls, reservation_id: int) -> dict[str, Any]:
        try:
            response = requests.delete(
                f"{cls.DEFAULT_BASE_URL}/api/v1/bookings/{reservation_id}",
                timeout=5,
            )
            response_payload = cls._response_json(response)

            if 200 <= response.status_code < 300:
                return {
                    "success": True,
                    "source": "backend",
                    "status_code": response.status_code,
                    "response": response_payload or None,
                }

            return reservation_error(
                status_code=response.status_code,
                error_code=response_payload.get("error_code", "UNKNOWN_BACKEND_ERROR"),
                message=response_payload.get("message", "예약 삭제에 실패했습니다."),
                response=response_payload or None,
                next_action="retry_or_human_review" if response.status_code >= 500 else "human_review",
            )
        except (requests.RequestException, ValueError) as exc:
            if cls.USE_MOCK_BACKEND:
                return {
                    "success": True,
                    "source": "mock",
                    "status_code": 200,
                    "response": {"reservation_id": reservation_id, "deleted": True},
                }

            return reservation_error(
                error_code="BACKEND_UNAVAILABLE",
                message="백엔드 서버에 연결할 수 없습니다.",
                error=str(exc),
                next_action="retry_or_human_review",
            )

    @classmethod
    def update_payment(cls, reservation_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = requests.patch(
                f"{cls.DEFAULT_BASE_URL}/api/v1/payments/{reservation_id}",
                json=payload,
                timeout=5,
            )
            response_payload = cls._response_json(response)

            if 200 <= response.status_code < 300:
                return {
                    "success": True,
                    "source": "backend",
                    "status_code": response.status_code,
                    "response": response_payload or None,
                }

            return reservation_error(
                status_code=response.status_code,
                error_code=response_payload.get("error_code", "UNKNOWN_BACKEND_ERROR"),
                message=response_payload.get("message", "결제 상태 업데이트에 실패했습니다."),
                response=response_payload or None,
                next_action="retry_or_human_review" if response.status_code >= 500 else "human_review",
            )
        except (requests.RequestException, ValueError) as exc:
            if cls.USE_MOCK_BACKEND:
                return {
                    "success": True,
                    "source": "mock",
                    "status_code": 200,
                    "response": {
                        "reservation_id": reservation_id,
                        "updated_fields": payload,
                    },
                }

            return reservation_error(
                error_code="BACKEND_UNAVAILABLE",
                message="백엔드 서버에 연결할 수 없습니다.",
                error=str(exc),
                next_action="retry_or_human_review",
            )

    @classmethod
    def refund_payment(cls, reservation_id: int) -> dict[str, Any]:
        try:
            response = requests.post(
                f"{cls.DEFAULT_BASE_URL}/api/v1/payments/{reservation_id}/refund",
                timeout=5,
            )
            response_payload = cls._response_json(response)

            if 200 <= response.status_code < 300:
                return {
                    "success": True,
                    "source": "backend",
                    "status_code": response.status_code,
                    "response": response_payload or None,
                }

            return reservation_error(
                status_code=response.status_code,
                error_code=response_payload.get("error_code", "UNKNOWN_BACKEND_ERROR"),
                message=response_payload.get("message", "환불 처리에 실패했습니다."),
                response=response_payload or None,
                next_action="retry_or_human_review" if response.status_code >= 500 else "human_review",
            )
        except (requests.RequestException, ValueError) as exc:
            if cls.USE_MOCK_BACKEND:
                return {
                    "success": True,
                    "source": "mock",
                    "status_code": 200,
                    "response": {"reservation_id": reservation_id, "refunded": True},
                }

            return reservation_error(
                error_code="BACKEND_UNAVAILABLE",
                message="백엔드 서버에 연결할 수 없습니다.",
                error=str(exc),
                next_action="retry_or_human_review",
            )

    @staticmethod
    def _response_json(response: requests.Response) -> dict[str, Any]:
        if not response.content:
            return {}
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _is_valid_date(date_str: str) -> bool:
        if not isinstance(date_str, str) or not date_str:
            return False
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            return False
        return True

    @classmethod
    def _load_mock(cls, filename: str) -> dict[str, Any]:
        if not cls.USE_MOCK_BACKEND:
            return {}
        try:
            return load_mock_json(filename)
        except Exception:
            return {}

    @staticmethod
    def _is_blank(value: Any) -> bool:
        return value is None or (isinstance(value, str) and not value.strip())
