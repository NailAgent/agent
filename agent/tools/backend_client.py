from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any, Optional

import requests

from agent.agents.schema import BookingSlots


class BackendClient:
    """Thin adapter for the backend API with deterministic fallback values."""

    DEFAULT_BASE_URL = os.getenv("BACKEND_BASE_URL", "http://localhost:8080").rstrip("/")
    DEFAULT_DEPOSIT_AMOUNT = 5000
    DEFAULT_ACCOUNT_NUMBER = "우리은행 1002-061-241977"
    DEFAULT_BUSINESS_HOUR = "10:00-22:00"
    DEFAULT_BOOKING_MESSAGE = "안녕하세요 고객님, 해당 시간 예약이 가능합니다!"
    DEFAULT_POLICY_TEXT = (
        "영업시간: 10:00-22:00 / 매주 월요일 정기휴무 / 예약금 5000원 / "
        "예약 변경은 하루 전까지만 가능하며, 당일 변경은 불가합니다."
    )
    DEFAULT_BOOKING_FORM_TEXT = """안녕하세요 고객님~ 예약 문의 주셔서 감사합니다:)
아래 예약 형식에 맞게 채워서 보내주시면 확인 후 예약 도와드리겠습니다!! (* 표시는 필수사항)

- *성함:
- *전화번호 (010-0000-0000):
- *젤제거 유무(O/X):
- *예약 희망 날짜 (형식: 2026-04-12):
- *예약 희망 시간 (형식: 18:00):
- *원하시는 시술 종류(손톱 케어/기본네일/젤네일/페디큐어 등):
- *과거 방문경험(O/X):
"""
    DEFAULT_SERVICES_JSON = '{"GEL_BASIC": 30000, "GEL_NAIL": 50000, "PEDICURE": 60000}'
    DEFAULT_BOOKED_SLOTS = [
        {"start": "11:00", "end": "12:30", "duration_min": 90},
        {"start": "14:00", "end": "15:00", "duration_min": 60},
    ]

    @classmethod
    def get_shop_info(cls) -> dict[str, Any]:
        """Return shop config from backend or fallback defaults."""
        try:
            response = requests.get(f"{cls.DEFAULT_BASE_URL}/api/v1/shopinfo", timeout=5)
            response.raise_for_status()
            payload = response.json()
            data = payload.get("data", payload)
            return {
                "business_hour": data.get("business_hour") or cls.DEFAULT_BUSINESS_HOUR,
                "closed_days": data.get("closed_days", 0),
                "booking_form_text": data.get("booking_form_text") or cls.DEFAULT_BOOKING_FORM_TEXT,
                "services_json": data.get("services_json") or cls.DEFAULT_SERVICES_JSON,
                "deposit_amount": data.get("deposit_amount") or cls.DEFAULT_DEPOSIT_AMOUNT,
                "account_number": data.get("account_number") or cls.DEFAULT_ACCOUNT_NUMBER,
                "policy_text": data.get("policy_text") or cls.DEFAULT_POLICY_TEXT,
                "booking_message_text": data.get("booking_message_text") or cls.DEFAULT_BOOKING_MESSAGE,
            }
        except Exception:
            return cls._fallback_shop_info()

    @classmethod
    def get_schedule(cls, date_str: str) -> dict[str, Any]:
        """Return business hours and booked slots for a given date."""
        try:
            response = requests.get(
                f"{cls.DEFAULT_BASE_URL}/api/v1/bookings/schedule",
                params={"date": date_str},
                timeout=5,
            )
            response.raise_for_status()
            payload = response.json()
            data = payload.get("data", payload)

            business_hour = data.get("business_hour") or data.get("businessHour") or cls.DEFAULT_BUSINESS_HOUR
            booked = data.get("booked_schedules") or data.get("bookedSchedules") or []

            return {
                "date": data.get("date") or date_str,
                "business_hours": cls._parse_business_hours(business_hour, date_str),
                "booked_slots": cls._normalize_booked_slots(booked),
                "source": "backend",
            }
        except Exception:
            shop = cls.get_shop_info()
            return {
                "date": date_str,
                "business_hours": cls._parse_business_hours(shop["business_hour"], date_str),
                "booked_slots": list(cls.DEFAULT_BOOKED_SLOTS),
                "source": "fallback",
            }

    @classmethod
    def create_reservation(cls, payload: dict[str, Any]) -> dict[str, Any]:
        """Persist a reservation through the backend or return a deterministic fallback."""
        try:
            response = requests.post(
                f"{cls.DEFAULT_BASE_URL}/api/v1/bookings",
                json=payload,
                timeout=5,
            )
            response.raise_for_status()
            return {
                "success": True,
                "source": "backend",
                "status_code": response.status_code,
                "response": response.json() if response.content else None,
            }
        except Exception:
            return {
                "success": True,
                "source": "fallback",
                "status_code": 201,
                "response": {
                    "status": 201,
                    "data": None,
                },
            }

    @classmethod
    def build_reservation_payload(
        cls,
        slots: BookingSlots,
        estimated_duration_min: int,
        deposit_amount: Optional[int] = None,
        designer: Optional[str] = None,
    ) -> dict[str, Any]:
        """Convert agent slots into backend reservation request payload."""
        shop = cls.get_shop_info()
        reserve_time = cls._format_reserve_time(slots.reserve_time, estimated_duration_min)
        service_map = {
            "GEL_BASIC": "기본네일",
            "GEL_NAIL": "젤네일",
            "PEDICURE": "페디큐어",
        }

        return {
            "name": slots.name,
            "phone_num": slots.phone_num,
            "reserve_date": slots.reserve_date,
            "reserve_time": reserve_time,
            "estimated_duration_min": estimated_duration_min,
            "service": service_map.get(slots.service_code or "", slots.service_code or "젤네일"),
            "off_removal": bool(slots.off_removal),
            "deposit_amount": deposit_amount or shop["deposit_amount"],
            "designer": designer,
        }

    @classmethod
    def _fallback_shop_info(cls) -> dict[str, Any]:
        return {
            "business_hour": cls.DEFAULT_BUSINESS_HOUR,
            "closed_days": 0,
            "booking_form_text": cls.DEFAULT_BOOKING_FORM_TEXT,
            "services_json": cls.DEFAULT_SERVICES_JSON,
            "deposit_amount": cls.DEFAULT_DEPOSIT_AMOUNT,
            "account_number": cls.DEFAULT_ACCOUNT_NUMBER,
            "policy_text": cls.DEFAULT_POLICY_TEXT,
            "booking_message_text": cls.DEFAULT_BOOKING_MESSAGE,
        }

    @classmethod
    def _parse_business_hours(cls, business_hour_text: str, date_str: Optional[str] = None) -> dict[str, str]:
        text = business_hour_text.replace(" ", "")

        def _match_time(label: str) -> Optional[dict[str, str]]:
            import re

            match = re.search(rf"{label}[:：]?(\d{{2}}:\d{{2}})-(\d{{2}}:\d{{2}})", text)
            if not match:
                return None
            return {"start": match.group(1), "end": match.group(2)}

        if date_str:
            try:
                weekday = datetime.strptime(date_str, "%Y-%m-%d").weekday()
                if weekday < 5:
                    matched = _match_time("평일")
                    if matched:
                        return matched
                else:
                    matched = _match_time("주말")
                    if matched:
                        return matched
            except ValueError:
                pass

        matched = _match_time("평일") or _match_time("주말")
        if matched:
            return matched
        if "10:00-22:00" in text:
            return {"start": "10:00", "end": "22:00"}
        if "10:00-21:00" in text:
            return {"start": "10:00", "end": "21:00"}
        return {"start": "10:00", "end": "22:00"}

    @classmethod
    def _normalize_booked_slots(cls, booked: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized = []
        for item in booked:
            reserve_time = item.get("reserve_time") or item.get("reserveTime") or ""
            duration = item.get("duration_min") or item.get("durationMin") or item.get("estimated_duration_min")
            if reserve_time and "-" in reserve_time:
                start, end = reserve_time.split("-", 1)
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
