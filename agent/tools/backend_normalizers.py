from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Optional

from agent.tools.backend_errors import reservation_list_error, schedule_error


def normalize_shop_info(
    payload: dict[str, Any],
    *,
    source: str,
    status_code: int | None = None,
) -> dict[str, Any]:
    data = payload.get("data", payload)
    if not isinstance(data, dict):
        data = {}

    services_price = data.get("services_price") or data.get("servicesPrice") or data.get("services_json")
    service_durations = data.get("service_durations") or data.get("serviceDurations")

    return {
        "success": True,
        "source": source,
        "status_code": status_code,
        "business_hour": data.get("business_hour"),
        "closed_days": data.get("closed_days"),
        "booking_form_text": data.get("booking_form_text"),
        "services_price": services_price,
        "services_json": services_price,
        "service_durations": service_durations,
        "deposit_amount": data.get("deposit_amount"),
        "account_number": data.get("account_number"),
        "policy_text": data.get("policy_text"),
        "booking_message_text": data.get("booking_message_text"),
    }


def normalize_schedule(
    payload: dict[str, Any],
    *,
    source: str,
    status_code: int | None = None,
    date_str: str,
) -> dict[str, Any]:
    data = payload.get("data", payload)
    if not isinstance(data, dict):
        return schedule_error(
            date_str,
            status_code=status_code,
            error_code="INVALID_SCHEDULE_RESPONSE",
            message="예약 스케줄 응답 data 형식이 올바르지 않습니다.",
        )

    business_hour = data.get("business_hour") or data.get("businessHour")
    if not business_hour:
        return schedule_error(
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
        return schedule_error(
            date_str,
            status_code=status_code,
            error_code="INVALID_SCHEDULE_RESPONSE",
            message="예약 스케줄 응답에 booked_schedules가 없습니다.",
        )

    if not isinstance(booked, list):
        return schedule_error(
            date_str,
            status_code=status_code,
            error_code="INVALID_SCHEDULE_RESPONSE",
            message="예약 스케줄 응답의 booked_schedules 형식이 올바르지 않습니다.",
        )

    try:
        business_hours = parse_business_hours(business_hour, date_str)
    except ValueError as exc:
        return schedule_error(
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
        "booked_slots": normalize_booked_slots(booked),
    }


def normalize_reservation_list(
    payload: dict[str, Any],
    *,
    source: str,
    status_code: int | None = None,
    page: int,
) -> dict[str, Any]:
    data = payload.get("data", payload)
    if not isinstance(data, dict):
        return reservation_list_error(
            page=page,
            status_code=status_code,
            error_code="INVALID_BOOKINGS_RESPONSE",
            message="예약 목록 응답 data 형식이 올바르지 않습니다.",
        )

    bookings = data.get("bookings")
    if bookings is None:
        return reservation_list_error(
            page=page,
            status_code=status_code,
            error_code="INVALID_BOOKINGS_RESPONSE",
            message="예약 목록 응답에 bookings가 없습니다.",
        )
    if not isinstance(bookings, list):
        return reservation_list_error(
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


def normalize_booked_slots(booked: list[dict[str, Any]]) -> list[dict[str, Any]]:
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


def parse_business_hours(business_hour_text: str, date_str: Optional[str] = None) -> dict[str, str]:
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

    plain_match = re.search(r"(\d{1,2}:\d{2})-(\d{1,2}:\d{2})", text)
    if plain_match:
        return {"start": plain_match.group(1), "end": plain_match.group(2)}

    raise ValueError(f"Could not parse business hours from: {business_hour_text}")


def format_reserve_time(reserve_time: Optional[str], estimated_duration_min: int) -> Optional[str]:
    if not reserve_time:
        return None

    try:
        start = datetime.strptime(reserve_time, "%H:%M")
        end = start + timedelta(minutes=estimated_duration_min)
        return f"{start.strftime('%H:%M')}-{end.strftime('%H:%M')}"
    except ValueError:
        return reserve_time


def normalize_kakao_customer(
    payload: dict[str, Any],
    *,
    source: str,
    status_code: int | None = None,
) -> dict[str, Any]:
    data = payload.get("data", payload)
    if not isinstance(data, dict):
        data = {}

    return {
        "success": True,
        "source": source,
        "status_code": status_code,
        "is_existing": data.get("is_existing") or data.get("isExisting"),
        "kakao_user_id": data.get("kakao_user_id") or data.get("kakaoUserId"),
        "plusfriend_user_key": data.get("plusfriend_user_key") or data.get("plusfriendUserKey"),
        "name": data.get("name"),
        "phone_num": data.get("phone_num") or data.get("phoneNum"),
    }
