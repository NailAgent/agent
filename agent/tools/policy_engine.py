from datetime import datetime, time


class PolicyEngine:
    """Engine that deterministic business rules of nail shop"""

    OPENING_HOUR = time(10, 0)
    CLOSING_HOUR = time(22, 0)
    CLOSED_DAYS = [0]  # 0 = Monday (fallback)

    SERVICE_DURATIONS = {
        "GEL_BASIC": 30,
        "GEL_NAIL": 60,
        "PEDICURE": 60,
        "REMOVAL_ADDON": 30,
    }

    @classmethod
    def _parse_closed_days(cls, closed_days) -> list[int]:
        """shop_info의 closed_days를 정수 리스트로 변환. DB는 단일 int로 반환."""
        if closed_days is None:
            return cls.CLOSED_DAYS
        if isinstance(closed_days, int):
            return [closed_days]
        if isinstance(closed_days, list):
            return [int(d) for d in closed_days]
        return cls.CLOSED_DAYS

    @classmethod
    def _parse_service_durations(cls, service_durations) -> dict[str, int]:
        """shop_info의 service_durations 문자열을 파싱. 실패 시 하드코딩 값 사용.
        기대 형식 예시: "GEL_BASIC:30,GEL_NAIL:60,PEDICURE:60,REMOVAL_ADDON:30"
        """
        if not service_durations or not isinstance(service_durations, str):
            return cls.SERVICE_DURATIONS
        try:
            parsed = {}
            for item in service_durations.split(","):
                if ":" in item:
                    key, val = item.strip().split(":", 1)
                    parsed[key.strip()] = int(val.strip())
            if parsed:
                parsed.setdefault("REMOVAL_ADDON", cls.SERVICE_DURATIONS["REMOVAL_ADDON"])
                return parsed
        except (ValueError, AttributeError):
            pass
        return cls.SERVICE_DURATIONS

    @classmethod
    def calculate_duration(cls, service_code: str, needs_removal: bool, service_durations=None) -> int:
        """Calculates total duration of the service."""
        durations = cls._parse_service_durations(service_durations)
        duration = durations.get(service_code, 60)
        if needs_removal:
            duration += durations.get("REMOVAL_ADDON", 30)
        return duration

    @classmethod
    def time_to_minutes(cls, t: time) -> int:
        return t.hour * 60 + t.minute

    @classmethod
    def validate_reservation(
        cls,
        date_str: str,
        time_str: str,
        duration: int,
        booked_slots: list,
        business_hours: dict | None = None,
        closed_days=None,
    ) -> dict:
        """Validate reservation time against business rules and existing bookings."""
        if not date_str or not time_str:
            return {"valid": False, "reason": "날짜와 시간이 입력되지 않았습니다."}

        try:
            req_date = datetime.strptime(date_str, "%Y-%m-%d")
            req_start_time = datetime.strptime(time_str, "%H:%M").time()
            req_start_min = cls.time_to_minutes(req_start_time)
            req_end_min = req_start_min + duration

            # 1. 휴무일 확인 (DB 값 우선)
            closed = cls._parse_closed_days(closed_days)
            if req_date.weekday() in closed:
                return {"valid": False, "reason": "해당 요일은 휴무일입니다."}

            # 2. 영업시간 확인
            if business_hours and business_hours.get("start") and business_hours.get("end"):
                open_time = datetime.strptime(business_hours["start"], "%H:%M").time()
                close_time = datetime.strptime(business_hours["end"], "%H:%M").time()
            else:
                open_time = cls.OPENING_HOUR
                close_time = cls.CLOSING_HOUR

            open_min = cls.time_to_minutes(open_time)
            close_min = cls.time_to_minutes(close_time)
            if req_start_min < open_min or req_end_min > close_min:
                return {
                    "valid": False,
                    "reason": f"영업시간({open_time.strftime('%H:%M')}~{close_time.strftime('%H:%M')}) 외의 시간입니다.",
                }

            # 3. 기존 예약과 충돌 확인
            for slot in booked_slots:
                slot_start = cls.time_to_minutes(datetime.strptime(slot["start"], "%H:%M").time())
                slot_end = cls.time_to_minutes(datetime.strptime(slot["end"], "%H:%M").time())
                if req_start_min < slot_end and slot_start < req_end_min:
                    return {"valid": False, "reason": "해당 시간에는 이미 예약이 있습니다."}

            return {"valid": True, "reason": "예약 가능합니다."}

        except ValueError:
            return {"valid": False, "reason": "날짜 또는 시간 형식이 잘못되었습니다."}

    @classmethod
    def get_available_recommendations(cls, business_hours: dict, booked_slots: list, duration: int) -> list:
        """Finds available time slots by looking for gaps."""
        open_min = cls.time_to_minutes(datetime.strptime(business_hours["start"], "%H:%M").time())
        close_min = cls.time_to_minutes(datetime.strptime(business_hours["end"], "%H:%M").time())

        timeline = [0] * (close_min - open_min)
        for slot in booked_slots:
            s = cls.time_to_minutes(datetime.strptime(slot["start"], "%H:%M").time()) - open_min
            e = cls.time_to_minutes(datetime.strptime(slot["end"], "%H:%M").time()) - open_min
            for i in range(max(0, s), min(len(timeline), e)):
                timeline[i] = 1

        recommendations = []
        count = 0
        for i in range(len(timeline)):
            if timeline[i] == 0:
                count += 1
                if count >= duration:
                    start_min = i - duration + 1 + open_min
                    if start_min % 30 == 0:
                        rec_time = f"{start_min // 60:02d}:{start_min % 60:02d}"
                        recommendations.append(rec_time)
            else:
                count = 0

        return recommendations[:3]
