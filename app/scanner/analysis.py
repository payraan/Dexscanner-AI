import pandas as pd
from typing import Optional, Dict, List, Tuple
from app.scanner.data_provider import data_provider
from app.scanner.strategies import trading_strategies
from app.scanner.zone_detector import zone_detector
from app.scanner.timeframe_selector import get_timeframe_from_data
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
        and stateful Fibonacci & Zone engines.
        """
        if token_data['volume_24h'] < self.min_volume_threshold:
            return None, None

        try:
            # مرحله ۱: دریافت داده‌های اولیه برای تخمین سن
            initial_df = await data_provider.fetch_ohlcv(
                token_data['pool_id'], timeframe="hour", aggregate="1", limit=200
            )

            if initial_df is None or initial_df.empty or len(initial_df) < 5:
                return None, None

            # مرحله ۲: تعیین تایم‌فریم بهینه
            timeframe, aggregate = get_timeframe_from_data(initial_df)
            
            # مرحله ۳: دریافت داده‌های نهایی با تایم‌فریم بهینه
            if timeframe == "hour" and aggregate == "1":
                df = initial_df
            else:
                limit_map = {
                    ("minute", "1"): 300, ("minute", "5"): 200, ("minute", "15"): 150,
                    ("hour", "4"): 100, ("hour", "12"): 80, ("day", "1"): 60
                }
                limit_count = limit_map.get((timeframe, aggregate), 100)
                df = await data_provider.fetch_ohlcv(
                    token_data['pool_id'], timeframe=timeframe, aggregate=aggregate, limit=limit_count
                )

            if df is None or df.empty or len(df) < 20:
                return None, None

            # مرحله ۴: یکپارچه‌سازی با موتورهای هوشمند
            fibo_state = None
            async for session in get_db():
                fibo_state = await fibonacci_engine.get_or_create_state(
                    session, token_data['address'], f"{timeframe}_{aggregate}", df
                )

            # --- مرحله ۵: اجرای تحلیل تکنیکال نهایی ---
            zones = zone_detector.find_support_resistance_zones(df)
            
            # --- تغییر کلیدی: ارسال zones و token_address به استراتژی‌ها ---
            detected_strategies = await trading_strategies.evaluate_all_strategies(
                df, zones, token_data['address']
            )

            if not detected_strategies and token_data['volume_24h'] > 1000000:
                detected_strategies.append({
                    'signal': 'high_volume', 'strength': min(token_data['volume_24h'] / 1000000, 10.0)
                })

            # مرحله ۶: آماده‌سازی و بازگشت نتیجه
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
                    'fibonacci_state': {
                        'high': fibo_state.high_point, 'low': fibo_state.low_point,
                        'target1': fibo_state.target1_price, 'target2': fibo_state.target2_price,
                        'target3': fibo_state.target3_price, 'status': fibo_state.status
                    } if fibo_state else None
                }
                return signal_data, df

        except Exception as e:
            logger.error(f"Error analyzing {token_data.get('symbol', 'Unknown')}: {e}", exc_info=True)
        
        return None, None

    # بخش health check شما بدون تغییر باقی می‌ماند
    async def quick_health_check(self, token_data: Dict) -> bool:
        try:
            df = await data_provider.fetch_ohlcv(
                token_data['pool_id'], timeframe="minute", aggregate="5", limit=20
            )
            if df is None or df.empty: return False
            max_price = df['high'].max()
            current_price = df['close'].iloc[-1]
            if max_price > 0 and ((max_price - current_price) / max_price) > 0.8:
                return False
            if df['close'].std() < current_price * 0.001:
                return False
            return True
        except Exception:
            return True

analysis_engine = AnalysisEngine()
