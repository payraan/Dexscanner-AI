import pandas as pd
from typing import Optional, Dict, List, Tuple
from app.scanner.data_provider import data_provider
from app.scanner.strategies import trading_strategies
from app.scanner.zone_detector import zone_detector
from app.scanner.timeframe_selector import get_dynamic_timeframe, get_timeframe_from_data
from app.database.session import get_db
from app.database.models import Token
from sqlalchemy import select
import logging

logger = logging.getLogger(__name__)

class AnalysisEngine:
    def __init__(self):
        self.min_volume_threshold = 100000  # $100k minimum volume

    async def analyze_token(self, token_data: Dict) -> Tuple[Optional[Dict], Optional[pd.DataFrame]]:
        """
        Analyze a single token for trading signals using smart dynamic timeframe selection.
        این نسخه بهینه شده ابتدا سن واقعی توکن را از داده‌ها تخمین می‌زند.
        """

        # فیلتر حجم اولیه
        if token_data['volume_24h'] < self.min_volume_threshold:
            logger.debug(f"Skipping {token_data['symbol']} - Volume too low: ${token_data['volume_24h']:,.0f}")
            return None, None

        try:
            # مرحله 1: دریافت داده‌های اولیه برای تخمین سن توکن
            # از 1-hour استفاده می‌کنیم که هم سریع است و هم برای تخمین سن کافی است
            logger.info(f"Fetching initial data for {token_data['symbol']} to estimate age...")
            
            initial_df = await data_provider.fetch_ohlcv(
                token_data['pool_id'],
                timeframe="hour",
                aggregate="1",
                limit=200  # 200 کندل = حدود 8 روز، کافی برای تخمین
            )

            if initial_df is None or initial_df.empty or len(initial_df) < 5:
                logger.warning(f"No sufficient initial data for {token_data['symbol']}")
                return None, None

            # مرحله 2: تعیین timeframe بهینه بر اساس داده‌های واقعی
            timeframe, aggregate = get_timeframe_from_data(initial_df)
            
            # لاگ برای دیباگ
            if 'timestamp' in initial_df.columns and len(initial_df) >= 2:
                age_hours = (initial_df['timestamp'].iloc[-1] - initial_df['timestamp'].iloc[0]) / 3600
                age_days = age_hours / 24
                logger.info(
                    f"Token {token_data['symbol']} age: {age_days:.1f} days ({age_hours:.1f} hours) "
                    f"→ Selected timeframe: {aggregate}{timeframe[0].upper()}"
                )
            else:
                logger.info(f"Selected timeframe for {token_data['symbol']}: {aggregate}{timeframe[0].upper()}")

            # مرحله 3: اگر timeframe انتخابی با timeframe اولیه متفاوت است، داده جدید بگیر
            if timeframe == "hour" and aggregate == "1":
                # از همان داده‌های اولیه استفاده می‌کنیم
                df = initial_df
                logger.info(f"Using initial hourly data for {token_data['symbol']}")
            else:
                # داده‌های جدید با timeframe بهینه دریافت می‌کنیم
                logger.info(f"Fetching optimized {aggregate}{timeframe[0].upper()} data for {token_data['symbol']}...")
                
                # تعداد کندل مناسب برای هر timeframe
                if timeframe == "minute":
                    if aggregate == "1":
                        limit_count = 300  # 5 ساعت داده
                    elif aggregate == "5":
                        limit_count = 200  # حدود 17 ساعت
                    else:  # 15 minute
                        limit_count = 150  # حدود 37 ساعت
                elif timeframe == "hour":
                    if aggregate == "4":
                        limit_count = 100  # حدود 17 روز
                    elif aggregate == "12":
                        limit_count = 80   # حدود 40 روز
                    else:
                        limit_count = 100
                else:  # day
                    limit_count = 60  # 2 ماه
                
                df = await data_provider.fetch_ohlcv(
                    token_data['pool_id'],
                    timeframe=timeframe,
                    aggregate=aggregate,
                    limit=limit_count
                )

            # بررسی کیفیت داده‌های نهایی
            if df is None or df.empty or len(df) < 20:
                logger.warning(f"Insufficient data for analysis: {token_data['symbol']} - Only {len(df) if df is not None else 0} candles")
                return None, None

            # مرحله 4: انجام تحلیل تکنیکال
            logger.debug(f"Analyzing {token_data['symbol']} with {len(df)} candles of {aggregate}{timeframe[0].upper()} data")
            
            # محاسبه support/resistance zones
            zones = zone_detector.find_support_resistance_zones(df)
            logger.debug(f"Found {len(zones)} support/resistance zones for {token_data['symbol']}")

            # اجرای استراتژی‌های معاملاتی
            detected_strategies = trading_strategies.evaluate_all_strategies(df)
            
            # Fallback برای توکن‌های پرحجم بدون سیگنال
            if not detected_strategies and token_data['volume_24h'] > 1000000:
                detected_strategies = [{
                    'signal': 'high_volume',
                    'strength': min(token_data['volume_24h'] / 1000000, 10.0)
                }]
                logger.info(f"High volume fallback signal for {token_data['symbol']}")

            # مرحله 5: آماده‌سازی و بازگشت نتیجه
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
                    'timeframe': f"{aggregate}{timeframe[0].upper()}",  # فرمت بهتر: 5M, 1H, etc
                    'all_signals': [s['signal'] for s in detected_strategies],
                    'zones': zones,
                    'candle_count': len(df)  # برای دیباگ
                }
                
                logger.info(
                    f"Signal found for {token_data['symbol']}: "
                    f"{strongest['signal']} (strength: {strongest['strength']:.1f}) "
                    f"on {aggregate}{timeframe[0].upper()} timeframe"
                )
                
                return signal_data, df
            else:
                logger.debug(f"No signals detected for {token_data['symbol']}")

        except Exception as e:
            logger.error(f"Error analyzing {token_data['symbol']}: {str(e)}", exc_info=True)
        
        return None, None

    async def quick_health_check(self, token_data: Dict) -> bool:
        """
        بررسی سریع سلامت توکن قبل از تحلیل کامل
        """
        try:
            # دریافت چند کندل اخیر
            df = await data_provider.fetch_ohlcv(
                token_data['pool_id'],
                timeframe="minute",
                aggregate="5",
                limit=20
            )
            
            if df is None or df.empty:
                return False
            
            # بررسی rug pull (افت بیش از 80% در 20 کندل اخیر)
            max_price = df['high'].max()
            current_price = df['close'].iloc[-1]
            
            if max_price > 0:
                drop_ratio = (max_price - current_price) / max_price
                if drop_ratio > 0.8:
                    logger.warning(f"Potential rug pull detected for {token_data['symbol']}: {drop_ratio:.1%} drop")
                    return False
            
            # بررسی نقدینگی (حداقل نوسان قیمت)
            price_std = df['close'].std()
            if price_std < current_price * 0.001:  # کمتر از 0.1% نوسان
                logger.warning(f"Dead token detected {token_data['symbol']}: No price movement")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Health check error for {token_data['symbol']}: {e}")
            return True  # در صورت خطا، اجازه تحلیل می‌دهیم

analysis_engine = AnalysisEngine()
