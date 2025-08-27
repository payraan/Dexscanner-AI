import pandas as pd
from typing import List, Dict, Optional

# --- افزودن import های جدید ---
from app.scanner.zone_engine import zone_engine
from app.database.session import get_db

# تعریف آستانه‌ها برای تشخیص وضعیت
APPROACH_THRESHOLD = 0.02  # 2% فاصله برای نزدیک شدن
BREAKOUT_THRESHOLD = 0.005 # 0.5% عبور برای شکست قطعی
COOLDOWN_DISTANCE = 0.05   # 5% فاصله برای ریست شدن وضعیت

class TradingStrategies:
    
    def __init__(self):
        self.min_candles = 20
    
    async def stateful_zone_strategy(self, df: pd.DataFrame, zones: List[Dict], token_address: str) -> Optional[Dict]:
        """
        یک استراتژی هوشمند و دارای حافظه برای تحلیل نواحی حمایت و مقاومت.
        این تابع جایگزین استراتژی‌های momentum_breakout و support_bounce می‌شود.
        """
        if not zones or df.empty:
            return None

        current_price = df['close'].iloc[-1]
        
        async for session in get_db():
            for zone in zones:
                zone_price = zone.get('price')
                if not zone_price: continue

                zone_type = zone.get('type') # 'resistance' or 'support'

                # دریافت وضعیت قبلی این ناحیه از دیتابیس
                state_info = await zone_engine.get_zone_state(session, token_address, zone_price)
                current_state = state_info.current_state

                # محاسبه فاصله قیمت فعلی از ناحیه
                distance_from_zone = (current_price - zone_price) / zone_price
                abs_distance = abs(distance_from_zone)
                
                new_state = current_state
                signal_type = None

                # --- منطق تصمیم‌گیری بر اساس وضعیت ---

                # 1. اگر قیمت یک مقاومت را شکسته باشد
                if zone_type == 'resistance' and distance_from_zone > BREAKOUT_THRESHOLD:
                    if current_state != 'BROKEN_UP':
                        new_state = 'BROKEN_UP'
                        signal_type = 'resistance_breakout'

                # 2. اگر قیمت یک حمایت را شکسته باشد (ریزش)
                elif zone_type == 'support' and distance_from_zone < -BREAKOUT_THRESHOLD:
                    if current_state != 'BROKEN_DOWN':
                        new_state = 'BROKEN_DOWN'
                        signal_type = 'support_breakdown'

                # 3. اگر قیمت در حال تست یک ناحیه است
                elif abs_distance < APPROACH_THRESHOLD:
                    if current_state not in ['TESTING_SUPPORT', 'TESTING_RESISTANCE']:
                        new_state = 'TESTING_SUPPORT' if zone_type == 'support' else 'TESTING_RESISTANCE'
                        signal_type = 'support_test' if zone_type == 'support' else 'resistance_test'
                
                # 4. اگر قیمت از ناحیه دور شده باشد، وضعیت را ریست کن
                elif abs_distance > COOLDOWN_DISTANCE and current_state != 'IDLE':
                    new_state = 'IDLE'
                    await zone_engine.update_zone_state(session, token_address, zone_price, new_state, None, current_price)


                # اگر وضعیت تغییر کرده و باید سیگنال ارسال شود
                if new_state != current_state and signal_type:
                    await zone_engine.update_zone_state(session, token_address, zone_price, new_state, signal_type, current_price)
                    
                    return {
                        'signal': signal_type,
                        'strength': zone.get('score', 5.0) + 2.0, # امتیاز پایه + امتیاز تغییر وضعیت
                        'level': zone_price,
                        'zone_score': zone.get('score', 0)
                    }
        return None # هیچ سیگنال جدیدی یافت نشد

    def volume_surge(self, df: pd.DataFrame, multiplier: float = 3.0) -> Optional[Dict]:
        """سیگنال جهش حجم (این استراتژی بدون تغییر باقی می‌ماند)"""
        if len(df) < 10:
            return None
        
        avg_volume = df['volume'].iloc[-10:-1].mean()
        if avg_volume == 0: return None # جلوگیری از تقسیم بر صفر
        
        current_volume = df['volume'].iloc[-1]
        
        if current_volume > avg_volume * multiplier:
            return {
                'signal': 'volume_surge',
                'strength': min(current_volume / (avg_volume or 1), 10.0),
                'volume_ratio': current_volume / (avg_volume or 1)
            }
        return None

    # تابع اصلی که تمام استراتژی‌ها را فراخوانی می‌کند
    async def evaluate_all_strategies(self, df: pd.DataFrame, zones: List[Dict], token_address: str) -> List[Dict]:
        """تمام استراتژی‌های معاملاتی را ارزیابی می‌کند."""
        strategies = []
        
        # 1. اجرای استراتژی هوشمند نواحی
        zone_signal = await self.stateful_zone_strategy(df, zones, token_address)
        if zone_signal:
            strategies.append(zone_signal)
            
        # 2. اجرای استراتژی جهش حجم
        volume_result = self.volume_surge(df)
        if volume_result:
            strategies.append(volume_result)
            
        # استراتژی‌های دیگر مانند obv_uptrend و three_white_soldiers را می‌توانید در اینجا اضافه کنید
        
        strategies.sort(key=lambda x: x['strength'], reverse=True)
        return strategies

trading_strategies = TradingStrategies()
