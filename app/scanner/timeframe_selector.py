# payraan/dexscanner-ai/Dexscanner-AI-56ae75eafc4041d4e754980a10c7a604dca6258b/app/scanner/timeframe_selector.py

from datetime import datetime, timedelta
from typing import Tuple

def get_dynamic_timeframe(launch_date: datetime) -> Tuple[str, str]:
    """
    سیستم پیشرفته انتخاب تایم‌فریم بهینه بر اساس سن دقیق توکن.
    این تابع منطق درختی جدید را برای تفکیک دقیق سن توکن پیاده‌سازی می‌کند.
    """
    if not isinstance(launch_date, datetime):
        # Fallback in case launch_date is not a valid datetime object
        return ("hour", "1")

    age = datetime.utcnow() - launch_date
    
    # برای توکن‌های بسیار جدید که عمرشان کمتر از ۴ ساعت است
    if age < timedelta(hours=4):
        return ("minute", "1")  # چارت ۱ دقیقه

    # شرط اول شما: بین ۴ تا ۱۲ ساعت -> چارت ۵ دقیقه
    elif age < timedelta(hours=12):
        return ("minute", "5")

    # شرط دوم شما: بین ۱۲ تا ۲۴ ساعت -> چارت ۱۵ دقیقه
    elif age < timedelta(days=1):
        return ("minute", "15")

    # شرط سوم شما: بین ۱ تا ۳ روز -> چارت ۱ ساعته
    elif age < timedelta(days=3):
        return ("hour", "1")

    # شرط چهارم شما: بین ۳ تا ۷ روز -> چارت ۴ ساعته
    elif age < timedelta(days=7):
        return ("hour", "4")
        
    # شرط پنجم شما: بین ۷ تا ۳۰ روز -> چارت ۱۲ ساعته (این یک تایم‌فریم جدید و عالی است)
    elif age < timedelta(days=30):
        return ("hour", "12")

    # شرط ششم شما: بیشتر از ۳۰ روز -> چارت روزانه
    else:
        return ("day", "1")
