import pandas as pd
from typing import Optional, Dict, List, Tuple
from app.scanner.data_provider import data_provider
from app.scanner.strategies import trading_strategies
from app.scanner.zone_detector import zone_detector
from app.scanner.timeframe_selector import get_dynamic_timeframe
from app.database.session import get_db
from app.database.models import Token
from sqlalchemy import select
import logging

logger = logging.getLogger(__name__)

class AnalysisEngine:
   def __init__(self):
       self.min_volume_threshold = 100000  # $100k minimum volume

   async def analyze_token(self, token_data: Dict) -> Tuple[Optional[Dict], Optional[pd.DataFrame]]:
       """Analyze a single token for trading signals using dynamic timeframe"""

       # Basic volume filter
       if token_data['volume_24h'] < self.min_volume_threshold:
           return None, None

       # Get token launch date from database for dynamic timeframe
       timeframe, aggregate = "hour", "1"  # default fallback
       
       try:
           async for session in get_db():
               result = await session.execute(
                   select(Token).where(Token.address == token_data['address'])
               )
               token_record = result.scalar_one_or_none()
               if token_record and token_record.launch_date:
                   timeframe, aggregate = get_dynamic_timeframe(token_record.launch_date)
                   logger.info(f"Dynamic timeframe for {token_data['symbol']}: {timeframe}/{aggregate}")
               break
       except Exception as e:
           logger.warning(f"Failed to get dynamic timeframe for {token_data['symbol']}: {e}")

       # Get OHLCV data with dynamic timeframe
       df = await data_provider.fetch_ohlcv(
           token_data['pool_id'],
           timeframe=timeframe,
           aggregate=aggregate,
           limit=100
       )

       if df is None or df.empty or len(df) < 20:
           return None, None

       # Calculate support/resistance zones
       zones = zone_detector.find_support_resistance_zones(df)

       # Use advanced trading strategies
       detected_strategies = trading_strategies.evaluate_all_strategies(df)

       # Fallback to simple high volume check
       if not detected_strategies and token_data['volume_24h'] > 1000000:
           detected_strategies = [{
               'signal': 'high_volume',
               'strength': min(token_data['volume_24h'] / 1000000, 10.0)
           }]

       # Return strongest signal if any found
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
               'timeframe': f"{timeframe}/{aggregate}",
               'all_signals': [s['signal'] for s in detected_strategies],
               'zones': zones
           }
           
           return signal_data, df

       return None, None

analysis_engine = AnalysisEngine()
