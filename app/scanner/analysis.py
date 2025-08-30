import pandas as pd
from typing import Optional, Dict, List, Tuple
from app.scanner.data_provider import data_provider
from app.scanner.strategies import trading_strategies
from app.scanner.zone_detector import zone_detector
from app.scanner.timeframe_selector import get_dynamic_timeframe
from app.database.session import get_db
from app.scanner.fibonacci_engine import fibonacci_engine
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

class AnalysisEngine:
   def __init__(self):
       self.min_volume_threshold = 100000

   async def analyze_token(self, token_data: Dict) -> Tuple[Optional[Dict], Optional[pd.DataFrame]]:
       """
       Analyze a single token using its accurate creation date to select the optimal timeframe.
       """
       if token_data.get('volume_24h', 0) < self.min_volume_threshold:
           return None, None

       try:
           # --- مرحله ۱: دریافت تاریخ دقیق ایجاد استخر از API (با قابلیت کشینگ) ---
           pool_details = await data_provider.fetch_pool_details(token_data['pool_id'])
           if not pool_details or 'pool_created_at' not in pool_details:
               logger.warning(f"Could not get accurate creation date for {token_data.get('symbol', 'N/A')}")
               return None, None

           # تبدیل تاریخ از فرمت ISO به شی datetime پایتون
           launch_date = datetime.fromisoformat(pool_details['pool_created_at'].replace('Z', '+00:00'))
           
           # --- مرحله ۲: انتخاب تایم‌فریم بهینه بر اساس تاریخ دقیق ---
           timeframe, aggregate = get_dynamic_timeframe(launch_date)
           
           age_days = (datetime.now(timezone.utc) - launch_date).days
           logger.info(f"Token {token_data.get('symbol')} is {age_days} days old -> Selected timeframe: {aggregate}{timeframe[0].upper()}")

           # مرحله ۳: دریافت داده‌های قیمتی با تایم‌فریم صحیح و تعداد کندل مناسب
           limit_map = {
               ("minute", "1"): 300, ("minute", "5"): 200, ("minute", "15"): 150,
               ("hour", "1"): 200, ("hour", "4"): 150, ("hour", "12"): 100, ("day", "1"): 90
           }
           limit_count = limit_map.get((timeframe, aggregate), 100)
           df = await data_provider.fetch_ohlcv(
               token_data['pool_id'], timeframe=timeframe, aggregate=aggregate, limit=limit_count
           )

           if df is None or df.empty or len(df) < 20:
               logger.warning(f"Insufficient OHLCV data for {token_data.get('symbol')} on {timeframe}/{aggregate} timeframe.")
               return None, None

           # --- مراحل بعدی (فیبوناچی و استراتژی‌ها) بدون تغییر باقی می‌مانند ---
           fibo_state = None
           async for session in get_db():
               fibo_state = await fibonacci_engine.get_or_create_state(
                   session, token_data['address'], f"{timeframe}_{aggregate}", df
               )

           zones = zone_detector.find_support_resistance_zones(df)
           detected_strategies = await trading_strategies.evaluate_all_strategies(
               df, zones, token_data['address']
           )

           if not detected_strategies and token_data.get('volume_24h', 0) > 1000000:
               detected_strategies.append({
                   'signal': 'high_volume', 'strength': min(token_data.get('volume_24h', 0) / 1000000, 10.0)
               })

           if detected_strategies:
               strongest = detected_strategies[0]
               
               # Calculate Gem Score based on multiple factors
               gem_score = strongest.get('strength', 0) * 10  # Base technical score (0-100)
               
               # Add on-chain analysis scores if available
               if 'holder_stats' in token_data:
                   holder_stats = token_data['holder_stats']
                   # Better distribution = higher score
                   gem_score += holder_stats.get('distribution_score', 0) * 0.3
                   
                   # Log metrics for monitoring
                   logger.info(f"Token {token_data.get('symbol')} - Concentration: {holder_stats.get('top_10_concentration')}%, Distribution Score: {holder_stats.get('distribution_score')}")
               
               if 'liquidity_stats' in token_data:
                   liquidity_stats = token_data['liquidity_stats']
                   # Positive flow and stability = higher score
                   if liquidity_stats.get('net_flow_24h_usd', 0) > 0:
                       gem_score += 10
                   if liquidity_stats.get('liquidity_stability_ratio', 0) > 1.5:
                       gem_score += 10
               
               # Only send signal if gem score is high enough
               if gem_score < 50:
                   logger.info(f"Skipping {token_data.get('symbol')} - Low gem score: {gem_score:.1f}")
                   return None, None
               
               signal_data = {
                   'token': token_data.get('symbol'), 'address': token_data.get('address'),
                   'pool_id': token_data.get('pool_id'), 'signal_type': strongest.get('signal'),
                   'strength': strongest.get('strength'), 'volume_24h': token_data.get('volume_24h'),
                   'price': token_data.get('price_usd'), 'timeframe': f"{aggregate}{timeframe[0].upper()}",
                   'all_signals': [s.get('signal') for s in detected_strategies], 'zones': zones,
                   'gem_score': round(gem_score, 1),
                   'holder_concentration': token_data.get('holder_stats', {}).get('top_10_concentration'),
                   'liquidity_flow': token_data.get('liquidity_stats', {}).get('net_flow_24h_usd'),
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

analysis_engine = AnalysisEngine()
