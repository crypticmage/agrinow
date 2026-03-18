from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))

def get_ist_now():
    """Returns the current datetime in IST."""
    return datetime.now(IST)

def get_ist_date():
    """Returns the current date in IST."""
    return get_ist_now().date()
