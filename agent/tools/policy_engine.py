from datetime import datetime, time

class PolicyEngine:
    """Deterministic rules for the nail shop."""
    
    OPENING_HOUR = time(10, 0)
    CLOSING_HOUR = time(22, 0)
    CLOSED_DAYS = [0] # 0 = Monday
    
    # Service durations in minutes
    SERVICE_DURATIONS = {
        "GEL_BASIC": 30,
        "GEL_NAIL": 60,
        "PEDICURE": 60,
        "REMOVAL_ADDON": 30
    }

    @classmethod
    def validate_time(cls, date_str: str, time_str: str) -> dict:
        """Checks if the requested time is within opening hours and not on a closed day."""
        try:
            req_date = datetime.strptime(date_str, "%Y-%m-%d")
            req_time = datetime.strptime(time_str, "%H:%M").time()
            
            # Check closed day
            if req_date.weekday() in cls.CLOSED_DAYS:
                return {"valid": False, "reason": "We are closed on Mondays."}
            
            # Check opening hours
            if not (cls.OPENING_HOUR <= req_time < cls.CLOSING_HOUR):
                return {"valid": False, "reason": f"We are open from {cls.OPENING_HOUR.strftime('%H:%M')} to {cls.CLOSING_HOUR.strftime('%H:%M')}."}
            
            return {"valid": True, "reason": "Time is available."}
        except ValueError:
            return {"valid": False, "reason": "Invalid date or time format."}

    @classmethod
    def calculate_duration(cls, service_code: str, needs_removal: bool) -> int:
        """Calculates total duration of the service."""
        duration = cls.SERVICE_DURATIONS.get(service_code, 60)
        if needs_removal:
            duration += cls.SERVICE_DURATIONS["REMOVAL_ADDON"]
        return duration
