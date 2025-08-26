from datetime import datetime, timedelta
from typing import Tuple

def get_dynamic_timeframe(launch_date: datetime) -> Tuple[str, str]:
    """
    Select optimal timeframe based on token age
    Returns: (timeframe, aggregate) tuple
    """
    age = datetime.utcnow() - launch_date
    
    if age < timedelta(hours=4):
        return ("minute", "1")        # Very fresh: 1min candles
    elif age < timedelta(hours=12):
        return ("minute", "5")        # Fresh: 5min candles
    elif age < timedelta(days=1):
        return ("minute", "15")       # Day old: 15min candles
    elif age < timedelta(days=3):
        return ("hour", "1")          # Few days: 1h candles
    elif age < timedelta(days=7):
        return ("hour", "4")          # Week old: 4h candles
    else:
        return ("day", "1")           # Mature: daily candles
