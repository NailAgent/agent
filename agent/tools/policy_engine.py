import re
from datetime import datetime, time
from zoneinfo import ZoneInfo


class PolicyEngine:
    """Engine that deterministic business rules of nail shop"""

    SHOP_TZ = ZoneInfo("Asia/Seoul")  # 서버 시간대와 무관하게 샵 기준(한국) 시각으로 판단
    OPENING_HOUR = time(10, 0)
    CLOSING_HOUR = time(22, 0)
    CLOSED_DAYS = [0]  # Python weekday 0 = Monday (샵 정보에 휴무일 값이 없을 때)
    WEEKDAY_NAMES = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]

    SERVICE_DURATIONS = {
        "GEL_BASIC": 30,
        "GEL_NAIL": 60,
        "PEDICURE": 60,
        "REMOVAL_ADDON": 30,
    }
    # 백엔드 service_durations에 쓰이는 시술명 (공백 제거 후 비교)
    SERVICE_NAME_CODES = {
        "젤네일": "GEL_NAIL",
        "기본네일": "GEL_BASIC",
        "기본케어": "GEL_BASIC",
        "손톱케어": "GEL_BASIC",
        "페디큐어": "PEDICURE",
        "젤제거": "REMOVAL_ADDON",
        "기존젤네일제거": "REMOVAL_ADDON",
        "제거": "REMOVAL_ADDON",
    }

    @classmethod
    def _parse_closed_days(cls, closed_days) -> list[int]:
        """shop_info의 closed_days(백엔드 값)를 Python weekday 리스트(0=월요일)로 바꾼다.

        백엔드는 1=월요일로 저장한다 (data.sql·API 예시 기준). 일요일을 0(JavaScript getDay)으로 저장하든
        7(ISO)로 저장하든 (값 - 1) % 7이면 같은 요일이 되므로 어느 쪽이어도 맞게 읽는다.
        DB는 단일 int로 반환하지만 여러 요일(list)도 받는다.
        """
        if closed_days is None:
            return cls.CLOSED_DAYS
        values = closed_days if isinstance(closed_days, list) else [closed_days]
        try:
            return [(int(d) - 1) % 7 for d in values]
        except (TypeError, ValueError):
            return cls.CLOSED_DAYS

    @classmethod
    def closed_day_names(cls, closed_days) -> str:
        """closed_days(백엔드 값)를 "월요일" / "월요일, 일요일" 같은 안내용 문자열로 바꾼다."""
        return ", ".join(cls.WEEKDAY_NAMES[d] for d in sorted(set(cls._parse_closed_days(closed_days))))

    @classmethod
    def _parse_service_durations(cls, service_durations) -> dict[str, int]:
        """shop_info의 service_durations 문자열을 파싱. 읽지 못한 항목은 하드코딩 값을 쓴다.

        두 형식을 읽는다.
        - 백엔드(data.sql) 형식: "젤네일 60분 / 기본네일 45분 / 페디큐어 60분"
        - 코드 형식: "GEL_BASIC:30,GEL_NAIL:60,PEDICURE:60,REMOVAL_ADDON:30"
        """
        if not service_durations or not isinstance(service_durations, str):
            return cls.SERVICE_DURATIONS
        parsed = {}
        for item in re.split(r"[/,]", service_durations):
            match = re.match(r"\s*([^\d:]+?)\s*:?\s*(\d+)\s*분?\s*$", item)
            if not match:
                continue
            name, minutes = match.group(1).strip(), int(match.group(2))
            code = name if name in cls.SERVICE_DURATIONS else cls.SERVICE_NAME_CODES.get(name.replace(" ", ""))
            if code:
                parsed[code] = minutes
        return {**cls.SERVICE_DURATIONS, **parsed} if parsed else cls.SERVICE_DURATIONS

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
    def now(cls) -> datetime:
        """샵 기준(한국) 현재 시각."""
        return datetime.now(cls.SHOP_TZ)

    @classmethod
    def _to_shop_time(cls, now: datetime | None) -> datetime:
        """비교 기준 시각을 한국 시각으로 맞춘다. 시간대 없는 값은 한국 시각으로 본다."""
        if now is None:
            return cls.now()
        if now.tzinfo is None:
            return now.replace(tzinfo=cls.SHOP_TZ)
        return now.astimezone(cls.SHOP_TZ)

    @classmethod
    def validate_reservation(
        cls,
        date_str: str,
        time_str: str,
        duration: int,
        booked_slots: list,
        business_hours: dict | None = None,
        closed_days=None,
        now: datetime | None = None,
    ) -> dict:
        """Validate reservation time against business rules and existing bookings."""
        if not date_str or not time_str:
            return {"valid": False, "reason": "날짜와 시간이 입력되지 않았습니다."}

        try:
            req_date = datetime.strptime(date_str, "%Y-%m-%d")
            req_start_time = datetime.strptime(time_str, "%H:%M").time()
            req_start_min = cls.time_to_minutes(req_start_time)
            req_end_min = req_start_min + duration

            # 0. 지난 날짜·시각 확인 (한국 시각 기준)
            current = cls._to_shop_time(now)
            if req_date.date() < current.date():
                return {"valid": False, "reason": "이미 지난 날짜입니다."}
            if req_date.date() == current.date() and req_start_min <= cls.time_to_minutes(current.time()):
                return {"valid": False, "reason": "이미 지난 시간입니다."}

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
    def get_available_recommendations(
        cls,
        business_hours: dict,
        booked_slots: list,
        duration: int,
        date_str: str | None = None,
        now: datetime | None = None,
    ) -> list:
        """Finds available time slots by looking for gaps.

        date_str를 주면 지난 날짜는 추천하지 않고, 오늘이면 지금 이후 시간만 추천한다 (한국 시각 기준).
        """
        open_min = cls.time_to_minutes(datetime.strptime(business_hours["start"], "%H:%M").time())
        close_min = cls.time_to_minutes(datetime.strptime(business_hours["end"], "%H:%M").time())

        earliest_start = open_min
        if date_str:
            try:
                req_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                req_date = None
            if req_date:
                current = cls._to_shop_time(now)
                if req_date < current.date():
                    return []
                if req_date == current.date():
                    earliest_start = max(open_min, cls.time_to_minutes(current.time()) + 1)

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
                    if start_min % 30 == 0 and start_min >= earliest_start:
                        rec_time = f"{start_min // 60:02d}:{start_min % 60:02d}"
                        recommendations.append(rec_time)
            else:
                count = 0

        return recommendations[:3]
