

from datetime import date, datetime
from typing import Dict


def get_date(input_date: str = str(date.today())) -> Dict[str, str]:
    """
    Return current date/time and echo input date.

    Args:
        input_date: The date string to process or echo.
    """
    now = datetime.now()
    return {
        "current_date": str(date.today()),
        "now": now.strftime("%Y-%m-%d %H:%M:%S"),
        "input_date": input_date,
    }
