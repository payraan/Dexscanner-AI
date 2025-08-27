import pandas as pd
from typing import Optional, Dict, List, Tuple
from app.scanner.data_provider import data_provider
from app.scanner.strategies import trading_strategies
from app.scanner.zone_detector import zone_detector
from app.scanner.timeframe_selector import get_timeframe_from_data # تابع هوشمند شما حفظ شده است
from app.database.session import get_db
from app.database.models import Token
from sqlalchemy import select
import logging

# --- افزودن import های جدید ---
from app.scanner.fibonacci_engine import fibonacci_engine

logger = logging.getLogger(__name__)

class AnalysisEngine:
    def __init__(self):
        self.min_volume_threshold = 100000  # $100k minimum volume

    async def analyze_token(self, token_data: Dict) -> Tuple[Optional[Dict], Optional[pd.DataFrame]]:
        """
        Analyze a single token for trading signals using smart dynamic timeframe selection
        and stateful Fibonacci engine.
        """
        if token_data['volume_24h'] < self.min_volume_threshold:
            logger.debug(f"Skipping {token_data['symbol']} - Volume too low: ${token_data['volume_24h']:,.0f}")
            return None, None

        try:
            # مرحله 1: دریافت داده‌های اولیه برای تخمین سن توکن
            initial_df = await data_provider.fetch_ohlcv(
                token_data['pool_id'],
                timeframe="hour",
                aggregate="1",
                limit=200
            )

            if initial_df is None or initial_df.empty or len(initial_df) < 5:
                logger.warning(f"No sufficient initial data for {token_data['symbol']}")
                return None, None

            # مرحله 2: تعیین timeframe بهینه بر اساس داده‌های واقعی
            timeframe, aggregate = get_timeframe_from_data(initial_df)
            
            # لاگ کردن تایم‌فریم انتخابی
            age_hours = (initial_df['timestamp'].iloc[-1] - initial_df['timestamp'].iloc[0]) / 3600
            logger.info(
                f"Token {token_data['symbol']} age: {age_hours/24:.1f} days "
                f"→ Selected timeframe: {aggregate}{timeframe[0].upper()}"
            )

            # مرحله 3: دریافت داده‌های نهایی با timeframe بهینه
            if timeframe == "hour" and aggregate == "1":
                df = initial_df
            else:
                # تعیین تعداد کندل مناسب برای هر تایم‌فریم
                limit_map = {
                    ("minute", "1"): 300, ("minute", "5"): 200, ("minute", "15"): 150,
                    ("hour", "4"): 100, ("hour", "12"): 80, ("day", "1"): 60
                }
                limit_count = limit_map.get((timeframe, aggregate), 100)
                
                df = await data_provider.fetch_ohlcv(
                    token_data['pool_id'],
                    timeframe=timeframe,
                    aggregate=aggregate,
                    limit=limit_count
                )

            if df is None or df.empty or len(df) < 20:
                logger.warning(f"Insufficient final data for analysis: {token_data['symbol']}")
                return None, None

            # --- مرحله 4: یکپارچه‌سازی با موتور فیبوناچی ---
            fibo_state = None
            async for session in get_db(): # دریافت session دیتابیس
                fibo_state = await fibonacci_engine.get_or_create_state(
                    session, token_data['address'], f"{timeframe}_{aggregate}", df
                )

            # مرحله 5: انجام تحلیل تکنیکال
            zones = zone_detector.find_support_resistance_zones(df)
            detected_strategies = trading_strategies.evaluate_all_strategies(df)

            if not detected_strategies and token_data['volume_24h'] > 1000000:
                detected_strategies.append({
                    'signal': 'high_volume',
                    'strength': min(token_data['volume_24h'] / 1000000, 10.0)
                })

            # مرحله 6: آماده‌سازی و بازگشت نتیجه
            if detected_strategies:
                strongest = detected_strategies[0]
                
                signal_data = {
                    'token': token_data['symbol'],
                    'address': token_data['address'],
                    'pool_id': token_data['pool_id'],
                    'signal_type': strongest['signal'],
                    'strength': strongest['strength'],
                    'volume_24h': token_data['volume_24h'],
                    'price': token_data['price_usd'],
                    'timeframe': f"{aggregate}{timeframe[0].upper()}",
                    'all_signals': [s['signal'] for s in detected_strategies],
                    'zones': zones,
                    # --- افزودن داده‌های فیبوناچی به خروجی ---
                    'fibonacci_state': {
                        'high': fibo_state.high_point,
                        'low': fibo_state.low_point,
                        'target1': fibo_state.target1_price,
                        'target2': fibo_state.target2_price,
                        'target3': fibo_state.target3_price,
                        'status': fibo_state.status
                    } if fibo_state else None
                }
                
                logger.info(f"Signal found for {signal_data['token']}: {signal_data['signal_type']}")
                return signal_data, df

        except Exception as e:
            logger.error(f"Error analyzing {token_data.get('symbol', 'Unknown')}: {e}", exc_info=True)
        
        return None, None

# بخش health check شما بدون تغییر باقی می‌ماند
    async def quick_health_check(self, token_data: Dict) -> bool:
        """
        بررسی سریع سلامت توکن قبل از تحلیل کامل
        """
        try:
            df = await data_provider.fetch_ohlcv(
                token_data['pool_id'],
                timeframe="minute",
                aggregate="5",
                limit=20
            )
            
            if df is None or df.empty:
                return False
            
            max_price = df['high'].max()
            current_price = df['close'].iloc[-1]
            
            if max_price > 0:
                drop_ratio = (max_price - current_price) / max_price
                if drop_ratio > 0.8:
                    logger.warning(f"Potential rug pull detected for {token_data['symbol']}: {drop_ratio:.1%} drop")
                    return False
            
            price_std = df['close'].std()
            if price_std < current_price * 0.001:
                logger.warning(f"Dead token detected {token_data['symbol']}: No price movement")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Health check error for {token_data['symbol']}: {e}")
            return True

analysis_engine = AnalysisEngine()
