from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any, Optional
import re

import requests

from agent.agents.schema import BookingSlots
from agent.tools.mock_loader import load_mock_json


class BackendClient:
    """Thin adapter for the backend API with deterministic fallback values."""

    DEFAULT_BASE_URL = os.getenv("BACKEND_BASE_URL", "http://localhost:8080").rstrip("/")
    USE_MOCK_BACKEND = os.getenv("USE_MOCK_BACKEND", "false").lower() in {"1", "true", "yes", "on"}

    @classmethod
    def get_shop_info(cls) -> dict[str, Any]:
        """[샵정보 조회] Return shop config from backend or fallback defaults."""
        try:
            response = requests.get(f"{cls.DEFAULT_BASE_URL}/api/v1/shopinfo", timeout=5)
            payload = cls._response_json(response)

            # 200 : backend /api/v1/shopinfo data
            if response.status_code == 200:
                return cls._normalize_shop_info(payload, source="backend", status_code=response.status_code)

            mock = cls._mock_shop_info()
            if mock:
                return mock

            # 404 NOT FOUND
            return cls._shop_info_error(
                status_code=response.status_code,
                error_code=payload.get("error_code", "UNKNOWN_BACKEND_ERROR"),
                message=payload.get("message", "샵 정보를 불러올 수 없습니다."),
                next_action="retry_or_human_review" if response.status_code >= 500 else "human_review",
            )

        # 500 INTERNAL SERVER ERROR
        except (requests.RequestException, ValueError) as exc:
            mock = cls._mock_shop_info()
            if mock:
                return mock

            return cls._shop_info_error(
                error_code="BACKEND_UNAVAILABLE",
                message="백엔드 서버에 연결할 수 없습니다.",
                error=str(exc),
                next_action="retry_or_human_review",
            )

    @classmethod
    def get_schedule(cls, date_str: str) -> dict[str, Any]:
        """[예약 스케줄 조회] Return business hours and booked slots for a given date."""
        if not cls._is_valid_date(date_str):
            return cls._schedule_error(
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

            # 200 : backend /api/v1/bookings/schedule?date={date} data
            if response.status_code == 200:
                return cls._normalize_schedule(payload, source="backend", status_code=response.status_code, date_str=date_str)

            mock = cls._mock_schedule(date_str)
            if mock:
                return mock

            # 400 BAD REQUEST
            return cls._schedule_error(
                date_str,
                status_code=response.status_code,
                error_code=payload.get("error_code", "UNKNOWN_BACKEND_ERROR"),
                message=payload.get("message", "예약 스케줄을 불러올 수 없습니다."),
                next_action="retry_or_human_review" if response.status_code >= 500 else "human_review",
            )

        # 500 INTERNAL SERVER ERROR
        except (requests.RequestException, ValueError) as exc:
            if not cls.USE_MOCK_BACKEND:
                return cls._schedule_error(
                    date_str,
                    error_code="BACKEND_UNAVAILABLE",
                    message="백엔드 서버에 연결할 수 없습니다.",
                    error=str(exc),
                    next_action="retry_or_human_review",
                )

            mock = cls._mock_schedule(date_str)
            if mock:
                return mock

            return cls._schedule_error(
                date_str,
                error_code="BACKEND_UNAVAILABLE",
                message="백엔드 연결 실패 후 사용할 mock schedule도 없습니다.",
                error=str(exc),
                next_action="retry_or_human_review",
            )

    @classmethod
    def create_reservation(cls, payload: dict[str, Any]) -> dict[str, Any]:
        """[예약 생성] Persist a reservation through the backend or return a deterministic fallback."""
        try:
            response = requests.post(
                f"{cls.DEFAULT_BASE_URL}/api/v1/bookings",
                json=payload,
                timeout=5,
            )
            response_payload = cls._response_json(response)

            # 200 : backend /api/v1/bookings POST
            if 200 <= response.status_code < 300:
                return {
                    "success": True,
                    "source": "backend",
                    "status_code": response.status_code,
                    "response": response_payload or None,
                }

            # 400 BAD REQUEST
            return cls._reservation_error(
                status_code=response.status_code,
                error_code=response_payload.get("error_code", "UNKNOWN_BACKEND_ERROR"),
                message=response_payload.get("message", "예약 생성에 실패했습니다."),
                response=response_payload or None,
                next_action="retry_or_human_review" if response.status_code >= 500 else "human_review",
            )
            
        # 500 INTERNAL SERVER ERROR
        except (requests.RequestException, ValueError) as exc:
            if not cls.USE_MOCK_BACKEND:
                return cls._reservation_error(
                    error_code="BACKEND_UNAVAILABLE",
                    message="백엔드 서버에 연결할 수 없습니다.",
                    error=str(exc),
                    next_action="retry_or_human_review",
                )

            mock = cls._mock_create_booking()
            if mock:
                return mock

            return cls._reservation_error(
                error_code="BACKEND_UNAVAILABLE",
                message="백엔드 연결 실패 후 사용할 mock 예약 생성 응답도 없습니다.",
                error=str(exc),
                next_action="retry_or_human_review",
            )

    @classmethod
    def list_reservations(cls, page: int = 1, size: int = 100) -> dict[str, Any]:
        """[변경/취소/입금확인] Fetch a reservation page from the backend or fallback fixtures."""
        try:
            response = requests.get(
                f"{cls.DEFAULT_BASE_URL}/api/v1/bookings",
                params={"page": page, "size": size},
                timeout=5,
            )
            payload = cls._response_json(response)

            if response.status_code == 200:
                return cls._normalize_reservations(payload, source="backend", status_code=response.status_code, page=page)

            return cls._reservations_error(
                page=page,
                status_code=response.status_code,
                error_code=payload.get("error_code", "UNKNOWN_BACKEND_ERROR"),
                message=payload.get("message", "예약 목록을 불러올 수 없습니다."),
                response=payload or None,
                next_action="retry_or_human_review" if response.status_code >= 500 else "human_review",
            )
        except (requests.RequestException, ValueError) as exc:
            if not cls.USE_MOCK_BACKEND:
                return cls._reservations_error(
                    page=page,
                    error_code="BACKEND_UNAVAILABLE",
                    message="백엔드 서버에 연결할 수 없습니다.",
                    error=str(exc),
                    next_action="retry_or_human_review",
                )

            mock = cls._mock_reservations(page)
            if mock:
                return mock

            return cls._reservations_error(
                page=page,
                error_code="BACKEND_UNAVAILABLE",
                message="백엔드 연결 실패 후 사용할 mock 예약 목록도 없습니다.",
                error=str(exc),
                next_action="retry_or_human_review",
            )

    @classmethod
    def find_reservations(
        cls,
        name: Optional[str] = None,
        reserve_date: Optional[str] = None,
        reserve_time: Optional[str] = None,
        service: Optional[str] = None,
        visit_status: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """[변경/취소/입금확인] Search reservations using the list API or fallback fixtures."""
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
            if reserve_date and reserve_date != str(item.get("reserve_date", "")):
                return False
            if reserve_time:
                item_time = str(item.get("reserve_time", ""))
                if reserve_time not in item_time and item_time not in reserve_time:
                    return False
            if service and service not in str(item.get("service", "")):
                return False
            if visit_status and visit_status.upper() != str(item.get("visit_status", "")).upper():
                return False
            return True

        return [item for item in candidates if _matches(item)]

    @classmethod
    def format_reservation_summary(cls, reservation: dict[str, Any]) -> str:
        """Create a short Korean summary for a reservation."""
        return (
            f"[예약 #{reservation.get('id', '?')}] "
            f"{reservation.get('name', '알 수 없음')} | "
            f"{reservation.get('reserve_date', '날짜 미상')} | "
            f"{reservation.get('reserve_time', '시간 미상')} | "
            f"{reservation.get('service', '시술 미상')} | "
            f"{reservation.get('visit_status', '상태 미상')}"
        )

    @classmethod
    def build_reservation_payload(
        cls,
        slots: BookingSlots,
        estimated_duration_min: int,
        deposit_amount: Optional[int] = None,
        designer: Optional[str] = None,
    ) -> dict[str, Any]:
        """[예약 생성] Convert agent slots into backend reservation request payload."""
        shop = cls.get_shop_info() if deposit_amount is None else {}
        resolved_deposit_amount = deposit_amount if deposit_amount is not None else shop.get("deposit_amount")
        cls._validate_reservation_payload_inputs(slots, estimated_duration_min, resolved_deposit_amount)

        reserve_time = cls._format_reserve_time(slots.reserve_time, estimated_duration_min)
        service_map = {
            "GEL_BASIC": "기본네일",
            "GEL_NAIL": "젤네일",
            "PEDICURE": "페디큐어",
        }

        payload = {
            "name": slots.name,
            "phone_num": slots.phone_num,
            "reserve_date": slots.reserve_date,
            "reserve_time": reserve_time,
            "estimated_duration_min": estimated_duration_min,
            "service": service_map.get(slots.service_code or "", slots.service_code or "젤네일"),
            "off_removal": bool(slots.off_removal),
            "deposit_amount": resolved_deposit_amount,
            "designer": designer,
        }
        cls._validate_required_fields(
            payload,
            [
                "name",
                "phone_num",
                "reserve_date",
                "reserve_time",
                "estimated_duration_min",
                "service",
                "off_removal",
                "deposit_amount",
            ],
        )
        return payload

    @classmethod
    def _validate_reservation_payload_inputs(
        cls,
        slots: BookingSlots,
        estimated_duration_min: int,
        deposit_amount: int | None,
    ) -> None:
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
        if deposit_amount is None:
            missing_fields.append("deposit_amount")

        if missing_fields:
            raise ValueError(f"Missing required reservation fields: {', '.join(missing_fields)}")

    @classmethod
    def _validate_required_fields(cls, payload: dict[str, Any], required_fields: list[str]) -> None:
        missing_fields = [field_name for field_name in required_fields if cls._is_blank(payload.get(field_name))]
        if missing_fields:
            raise ValueError(f"Missing required reservation fields: {', '.join(missing_fields)}")

    @staticmethod
    def _is_blank(value: Any) -> bool:
        return value is None or (isinstance(value, str) and not value.strip())

    @staticmethod
    def _mock_data(filename: str) -> dict[str, Any]:
        try:
            payload = load_mock_json(filename)
        except Exception:
            return {}
        data = payload.get("data", payload)
        return data if isinstance(data, dict) else {}

    @classmethod
    def _mock_shop_info(cls) -> dict[str, Any]:
        if not cls.USE_MOCK_BACKEND:
            return {}

        try:
            payload = load_mock_json("shopinfo_200.json")
        except Exception:
            return {}
        if not payload:
            return {}
        return cls._normalize_shop_info(payload, source="mock", status_code=payload.get("status", 200))

    @classmethod
    def _mock_create_booking(cls) -> dict[str, Any]:
        if not cls.USE_MOCK_BACKEND:
            return {}

        try:
            payload = load_mock_json("create_booking_201.json")
        except Exception:
            return {}
        if not payload:
            return {}

        return {
            "success": True,
            "source": "mock",
            "status_code": payload.get("status", 201),
            "response": payload,
        }

    @classmethod
    def _mock_reservations(cls, page: int) -> dict[str, Any]:
        if not cls.USE_MOCK_BACKEND:
            return {}

        try:
            payload = load_mock_json("bookings_200.json")
        except Exception:
            return {}
        if not payload:
            return {}

        normalized = cls._normalize_reservations(payload, source="mock", status_code=payload.get("status", 200), page=page)
        return normalized if normalized.get("success") else {}

    @staticmethod
    def _normalize_shop_info(payload: dict[str, Any], *, source: str, status_code: int | None = None) -> dict[str, Any]:
        data = payload.get("data", payload)
        if not isinstance(data, dict):
            data = {}

        return {
            "success": True,
            "source": source,
            "status_code": status_code,
            "business_hour": data.get("business_hour"),
            "closed_days": data.get("closed_days"),
            "booking_form_text": data.get("booking_form_text"),
            "services_json": data.get("services_json"),
            "deposit_amount": data.get("deposit_amount"),
            "account_number": data.get("account_number"),
            "policy_text": data.get("policy_text"),
            "booking_message_text": data.get("booking_message_text"),
        }

    @staticmethod
    def _normalize_reservations(
        payload: dict[str, Any],
        *,
        source: str,
        status_code: int | None = None,
        page: int,
    ) -> dict[str, Any]:
        data = payload.get("data", payload)
        if not isinstance(data, dict):
            return BackendClient._reservations_error(
                page=page,
                status_code=status_code,
                error_code="INVALID_BOOKINGS_RESPONSE",
                message="예약 목록 응답 data 형식이 올바르지 않습니다.",
            )

        bookings = data.get("bookings")
        if bookings is None:
            return BackendClient._reservations_error(
                page=page,
                status_code=status_code,
                error_code="INVALID_BOOKINGS_RESPONSE",
                message="예약 목록 응답에 bookings가 없습니다.",
            )
        if not isinstance(bookings, list):
            return BackendClient._reservations_error(
                page=page,
                status_code=status_code,
                error_code="INVALID_BOOKINGS_RESPONSE",
                message="예약 목록 응답의 bookings 형식이 올바르지 않습니다.",
            )

        return {
            "success": True,
            "source": source,
            "status_code": status_code,
            "current_page": data.get("current_page") or data.get("currentPage") or page,
            "total_pages": data.get("total_pages") or data.get("totalPages") or 1,
            "bookings": bookings,
        }

    @classmethod
    def _mock_schedule(cls, date_str: str) -> dict[str, Any]:
        if not cls.USE_MOCK_BACKEND:
            return {}

        try:
            payload = load_mock_json("schedule_200.json")
        except Exception:
            return {}
        if not payload:
            return {}

        normalized = cls._normalize_schedule(payload, source="mock", status_code=payload.get("status", 200), date_str=date_str)
        return normalized if normalized.get("success") else {}

    @classmethod
    def _normalize_schedule(
        cls,
        payload: dict[str, Any],
        *,
        source: str,
        status_code: int | None = None,
        date_str: str,
    ) -> dict[str, Any]:
        data = payload.get("data", payload)
        if not isinstance(data, dict):
            return cls._schedule_error(
                date_str,
                status_code=status_code,
                error_code="INVALID_SCHEDULE_RESPONSE",
                message="예약 스케줄 응답 data 형식이 올바르지 않습니다.",
            )

        business_hour = data.get("business_hour") or data.get("businessHour")
        if not business_hour:
            return cls._schedule_error(
                date_str,
                status_code=status_code,
                error_code="INVALID_SCHEDULE_RESPONSE",
                message="예약 스케줄 응답에 business_hour가 없습니다.",
            )

        if "booked_schedules" in data:
            booked = data["booked_schedules"]
        elif "bookedSchedules" in data:
            booked = data["bookedSchedules"]
        else:
            return cls._schedule_error(
                date_str,
                status_code=status_code,
                error_code="INVALID_SCHEDULE_RESPONSE",
                message="예약 스케줄 응답에 booked_schedules가 없습니다.",
            )

        if not isinstance(booked, list):
            return cls._schedule_error(
                date_str,
                status_code=status_code,
                error_code="INVALID_SCHEDULE_RESPONSE",
                message="예약 스케줄 응답의 booked_schedules 형식이 올바르지 않습니다.",
            )

        try:
            business_hours = cls._parse_business_hours(business_hour, date_str)
        except ValueError as exc:
            return cls._schedule_error(
                date_str,
                status_code=status_code,
                error_code="INVALID_SCHEDULE_RESPONSE",
                message=str(exc),
            )

        return {
            "success": True,
            "source": source,
            "status_code": status_code,
            "date": data.get("date") or date_str,
            "business_hours": business_hours,
            "booked_slots": cls._normalize_booked_slots(booked),
        }

    @staticmethod
    def _shop_info_error(
        *,
        status_code: int | None = None,
        error_code: str = "BACKEND_UNAVAILABLE",
        message: str = "현재 샵 정보를 불러올 수 없습니다.",
        error: str | None = None,
        next_action: str = "human_review",
    ) -> dict[str, Any]:
        return {
            "success": False,
            "source": "backend_error",
            "status_code": status_code,
            "error_code": error_code,
            "message": message,
            "error": error,
            "next_action": next_action,
            "data": None,
        }

    @staticmethod
    def _reservation_error(
        *,
        status_code: int | None = None,
        error_code: str = "BACKEND_UNAVAILABLE",
        message: str = "예약 생성에 실패했습니다.",
        error: str | None = None,
        response: dict[str, Any] | None = None,
        next_action: str = "human_review",
    ) -> dict[str, Any]:
        return {
            "success": False,
            "source": "backend_error",
            "status_code": status_code,
            "error_code": error_code,
            "message": message,
            "error": error,
            "response": response,
            "next_action": next_action,
        }

    @staticmethod
    def _reservations_error(
        *,
        page: int,
        status_code: int | None = None,
        error_code: str = "BACKEND_UNAVAILABLE",
        message: str = "예약 목록을 불러올 수 없습니다.",
        error: str | None = None,
        response: dict[str, Any] | None = None,
        next_action: str = "human_review",
    ) -> dict[str, Any]:
        return {
            "success": False,
            "source": "backend_error",
            "status_code": status_code,
            "error_code": error_code,
            "message": message,
            "error": error,
            "response": response,
            "next_action": next_action,
            "current_page": page,
            "total_pages": 0,
            "bookings": [],
        }

    @classmethod
    def _schedule_error(
        cls,
        date_str: str,
        *,
        status_code: int | None = None,
        error_code: str = "BACKEND_UNAVAILABLE",
        message: str = "예약 스케줄을 불러올 수 없습니다.",
        error: str | None = None,
        next_action: str = "human_review",
    ) -> dict[str, Any]:
        return {
            "success": False,
            "date": date_str,
            "business_hours": {"start": "00:00", "end": "00:00"},
            "booked_slots": [],
            "source": "backend_error",
            "status_code": status_code,
            "error_code": error_code,
            "message": message,
            "error": error,
            "next_action": next_action,
            "data": None,
        }

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
    def _parse_business_hours(cls, business_hour_text: str, date_str: Optional[str] = None) -> dict[str, str]:
        """Normalize backend business hours for use by the policy engine."""

        if not business_hour_text:
            raise ValueError("business_hour is required")

        text = business_hour_text.replace(" ", "")

        def _match_time(label: str) -> Optional[dict[str, str]]:

            match = re.search(rf"{label}[:：]?(\d{{2}}:\d{{2}})-(\d{{2}}:\d{{2}})", text)
            if not match:
                return None
            return {"start": match.group(1), "end": match.group(2)}

        if date_str:
            try:
                weekday = datetime.strptime(date_str, "%Y-%m-%d").weekday()
            except ValueError as exc:
                raise ValueError(f"Invalid date_str format: {date_str}") from exc

            label = "평일" if weekday < 5 else "주말"
            matched = _match_time(label)

            if matched:
                return matched

        matched = _match_time("평일") or _match_time("주말")
        if matched:
            return matched

        # "평일", "주말" 언급이 없는 데이터에 대해서도 처리 가능
        plain_match = re.search(r"(\d{1,2}:\d{2})-(\d{1,2}:\d{2})", text)
        if plain_match:
            return {"start": plain_match.group(1), "end": plain_match.group(2)}

        raise ValueError(f"Could not parse business hours from: {business_hour_text}")

    @classmethod
    def _normalize_booked_slots(cls, booked: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Normalize reserve_time for use by the policy engine."""
        normalized = []
        for item in booked:
            reserve_time = item.get("reserve_time") or item.get("reserveTime") or ""
            duration = item.get("duration_min") or item.get("durationMin") or item.get("estimated_duration_min")
            if reserve_time and "-" in reserve_time:
                start, end = [part.strip() for part in reserve_time.split("-", 1)]
                normalized.append({"start": start, "end": end, "duration_min": duration or 0})
                continue

            start = item.get("start")
            end = item.get("end")
            if start and end:
                normalized.append({"start": start, "end": end, "duration_min": duration or 0})
        return normalized

    @classmethod
    def _format_reserve_time(cls, reserve_time: Optional[str], estimated_duration_min: int) -> Optional[str]:
        if not reserve_time:
            return None

        try:
            start = datetime.strptime(reserve_time, "%H:%M")
            end = start + timedelta(minutes=estimated_duration_min)
            return f"{start.strftime('%H:%M')}-{end.strftime('%H:%M')}"
        except ValueError:
            return reserve_time
