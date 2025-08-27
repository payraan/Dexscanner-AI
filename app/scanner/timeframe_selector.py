from datetime import datetime, timedelta
from typing import Tuple
import pandas as pd

def get_dynamic_timeframe(launch_date: datetime) -> Tuple[str, str]:
    """تابع قدیمی که دیگر استفاده نخواهد شد اما برای سازگاری باقی می‌ماند."""
    age = datetime.utcnow() - launch_date
    if age < timedelta(hours=4): return ("minute", "1")
    elif age < timedelta(hours=12): return ("minute", "5")
    elif age < timedelta(days=1): return ("minute", "15")
    elif age < timedelta(days=3): return ("hour", "1")
    elif age < timedelta(days=7): return ("hour", "4")
    elif age < timedelta(days=30): return ("hour", "12")
    else: return ("day", "1")

def get_timeframe_from_data(df: pd.DataFrame) -> Tuple[str, str]:
    """
    تابع جدید و هوشمند: تعیین تایم‌فریم بر اساس سن واقعی توکن از روی داده‌های OHLCV.
    """
    if df is None or df.empty or 'timestamp' not in df.columns or len(df) < 2:
        return ("hour", "1")
    
    first_ts, last_ts = df['timestamp'].min(), df['timestamp'].max()
    age_hours = (last_ts - first_ts) / 3600
    age_days = age_hours / 24
    
    if age_hours < 4: return ("minute", "1")
    elif age_hours < 12: return ("minute", "5")
    elif age_hours < 24: return ("minute", "15")
    elif age_days < 3: return ("hour", "1")
    elif age_days < 7: return ("hour", "4")
    elif age_days < 30: return ("hour", "12")
    else: return ("day", "1")
