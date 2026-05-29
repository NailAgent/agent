from __future__ import annotations

from typing import Any


def shop_info_error(
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


def schedule_error(
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


def reservation_error(
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


def reservation_list_error(
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


def customer_error(
    *,
    status_code: int | None = None,
    error_code: str = "BACKEND_UNAVAILABLE",
    message: str = "카카오 고객 정보를 불러올 수 없습니다.",
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
        "data": None,
    }
