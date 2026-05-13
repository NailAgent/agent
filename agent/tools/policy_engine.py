from datetime import datetime, time

class PolicyEngine:
    """Engine that deterministic business rules of nail shop"""
    
    OPENING_HOUR = time(10, 0)
    CLOSING_HOUR = time(22, 0)
    CLOSED_DAYS = [0] # 0 = Monday
    
    SERVICE_DURATIONS = {
        "GEL_BASIC": 30,
        "GEL_NAIL": 60,
        "PEDICURE": 60,
        "REMOVAL_ADDON": 30
    }

    @classmethod
    def calculate_duration(cls, service_code: str, needs_removal: bool) -> int:
        """Calculates total duration of the service."""
        duration = cls.SERVICE_DURATIONS.get(service_code, 60)
        if needs_removal:
            duration += cls.SERVICE_DURATIONS["REMOVAL_ADDON"]
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
    ) -> dict:
        """
        Validate the requested time overlaps with existing reservations and is within business hours
        """
        if not date_str or not time_str:
            return {"valid": False, "reason": "날짜와 시간이 입력되지 않았습니다."}
            
        try:
            req_date = datetime.strptime(date_str, "%Y-%m-%d")
            req_start_time = datetime.strptime(time_str, "%H:%M").time()
            req_start_min = cls.time_to_minutes(req_start_time)
            req_end_min = req_start_min + duration
            
            # 1. 요일 확인
            if req_date.weekday() in cls.CLOSED_DAYS:
                return {"valid": False, "reason": "매주 월요일은 정기 휴무입니다."}
            
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
                return {"valid": False, "reason": f"영업시간({open_time.strftime('%H:%M')}~{close_time.strftime('%H:%M')}) 외의 시간입니다."}
            
            # 3. 기존 예약과 충돌 확인 (백엔드 데이터 활용)
            for slot in booked_slots:
                slot_start = cls.time_to_minutes(datetime.strptime(slot['start'], "%H:%M").time())
                slot_end = cls.time_to_minutes(datetime.strptime(slot['end'], "%H:%M").time())
                
                # 시간 겹침 로직: (A_start < B_end) AND (B_start < A_end)
                if req_start_min < slot_end and slot_start < req_end_min:
                    return {"valid": False, "reason": "해당 시간에는 이미 예약이 있습니다."}
            
            return {"valid": True, "reason": "예약 가능합니다."}
            
        except ValueError:
            return {"valid": False, "reason": "날짜 또는 시간 형식이 잘못되었습니다."}

    @classmethod
    def get_available_recommendations(cls, business_hours: dict, booked_slots: list, duration: int) -> list:
        """
        Finds available time slots by looking for gaps.
        """
        open_min = cls.time_to_minutes(datetime.strptime(business_hours['start'], "%H:%M").time())
        close_min = cls.time_to_minutes(datetime.strptime(business_hours['end'], "%H:%M").time())
        
        # 1. Mark occupied time slots (1 = booked, 0 = available)
        timeline = [0] * (close_min - open_min)
        
        for slot in booked_slots:
            s = cls.time_to_minutes(datetime.strptime(slot['start'], "%H:%M").time()) - open_min
            e = cls.time_to_minutes(datetime.strptime(slot['end'], "%H:%M").time()) - open_min
            for i in range(max(0, s), min(len(timeline), e)):
                timeline[i] = 1
        
        # 2. Find continuous free slots
        recommendations = []
        count = 0
        for i in range(len(timeline)):
            if timeline[i] == 0:
                count += 1
                if count >= duration:
                    # Calculate start time (recommend every 30 minutes)
                    start_min = i - duration + 1 + open_min
                    if start_min % 30 == 0:
                        rec_time = f"{start_min//60:02d}:{start_min%60:02d}"
                        recommendations.append(rec_time)
            else:
                count = 0
        
        return recommendations[:3] # Top 3 recommendations
