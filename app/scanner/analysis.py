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

    def _calculate_gem_score(self, strongest_signal: Dict, holder_stats: Optional[Dict], liquidity_stats: Optional[Dict]) -> float:
        """
        Calculates the Gem Score based on a weighted system.
        Weights: Technical (45%), On-chain (35%), Liquidity (20%)
        """
        # 1. Technical Score (Max 45 points)
        # Strength is on a scale of 0-10, so we multiply by 4.5 to scale it to 45.
        technical_score = strongest_signal.get('strength', 0) * 4.5

        # 2. On-chain Score (Max 35 points)
        onchain_score = 0
        if holder_stats:
            # distribution_score is 0-100, scale it to 35 points.
            distribution_score = holder_stats.get('distribution_score', 0)
            onchain_score = (distribution_score / 100) * 35
            logger.info(f"Token On-chain stats - Concentration: {holder_stats.get('top_10_concentration')}%, Distribution Score: {distribution_score}")

        # 3. Liquidity Score (Max 20 points)
        liquidity_score = 0
        if liquidity_stats:
            # Assign 10 points for positive net flow
            if liquidity_stats.get('net_flow_24h_usd', 0) > 0:
                liquidity_score += 10
            # Assign 10 points for good stability (>1.5 means more adds than removes)
            if liquidity_stats.get('liquidity_stability_ratio', 0) > 1.5:
                liquidity_score += 10
        
        total_score = technical_score + onchain_score + liquidity_score
        
        # Ensure the score does not exceed 100
        return min(total_score, 100.0)

    async def analyze_token(self, token_data: Dict) -> Tuple[Optional[Dict], Optional[pd.DataFrame]]:
        """
        Analyze a single token using its accurate creation date to select the optimal timeframe.
        """
        if token_data.get('volume_24h', 0) < self.min_volume_threshold:
            return None, None

        try:
            pool_details = await data_provider.fetch_pool_details(token_data['pool_id'])
            if not pool_details or 'pool_created_at' not in pool_details:
                logger.warning(f"Could not get accurate creation date for {token_data.get('symbol', 'N/A')}")
                return None, None

            launch_date = datetime.fromisoformat(pool_details['pool_created_at'].replace('Z', '+00:00'))
            
            timeframe, aggregate = get_dynamic_timeframe(launch_date)
            
            age_days = (datetime.now(timezone.utc) - launch_date).days
            logger.info(f"Token {token_data.get('symbol')} is {age_days} days old -> Selected timeframe: {aggregate}{timeframe[0].upper()}")

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
                
                # --- NEW: Calculate Gem Score using the weighted system ---
                holder_stats = token_data.get('holder_stats')
                liquidity_stats = token_data.get('liquidity_stats')
                gem_score = self._calculate_gem_score(strongest, holder_stats, liquidity_stats)
                
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
                    'holder_concentration': holder_stats.get('top_10_concentration') if holder_stats else None,
                    'liquidity_flow': liquidity_stats.get('net_flow_24h_usd') if liquidity_stats else None,
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
