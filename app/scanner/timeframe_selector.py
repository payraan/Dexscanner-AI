# این فایل فقط حاوی یک تابع است که به درستی کار می‌کند
from datetime import datetime, timedelta, timezone
from typing import Tuple

def get_dynamic_timeframe(launch_date: datetime) -> Tuple[str, str]:
    """
    سیستم پیشرفته انتخاب تایم‌فریم بهینه بر اساس سن دقیق توکن.
    این نسخه برای حل مشکل منطقه زمانی (timezone) اصلاح شده است.
    """
    # بررسی می‌کند که ورودی حتما از نوع datetime باشد
    if not isinstance(launch_date, datetime):
        # اگر launch_date معتبر نباشد، یک تایم‌فریم پیش‌فرض برمی‌گرداند
        return ("hour", "1")

    # --- راه‌حل کلیدی: استفاده از datetime.now(timezone.utc) برای هماهنگ‌سازی مناطق زمانی ---
    # این کد زمان فعلی را به صورت "آگاه" از منطقه زمانی UTC دریافت می‌کند
    age = datetime.now(timezone.utc) - launch_date
    
    # بقیه منطق انتخاب تایم‌فریم بدون تغییر باقی می‌ماند
    if age < timedelta(hours=4):
        return ("minute", "1")
    elif age < timedelta(hours=12):
        return ("minute", "5")
    elif age < timedelta(days=1):
        return ("minute", "15")
    elif age < timedelta(days=3):
        return ("hour", "1")
    elif age < timedelta(days=7):
        return ("hour", "4")
    elif age < timedelta(days=30):
        return ("hour", "12")
    else:
        return ("day", "1")
