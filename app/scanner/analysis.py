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
        technical_score = strongest_signal.get('strength', 0) * 4.5
        onchain_score = 0
        if holder_stats:
            distribution_score = holder_stats.get('distribution_score', 0)
            onchain_score = (distribution_score / 100) * 35
            logger.info(f"Token On-chain stats - Concentration: {holder_stats.get('top_10_concentration')}%, Distribution Score: {distribution_score}")

        liquidity_score = 0
        if liquidity_stats:
            if liquidity_stats.get('net_flow_24h_usd', 0) > 0:
                liquidity_score += 10
            if liquidity_stats.get('liquidity_stability_ratio', 0) > 1.5:
                liquidity_score += 10
        
        total_score = technical_score + onchain_score + liquidity_score
        return min(total_score, 100.0)

    def _calculate_fib_retracement(self, high: float, low: float) -> Dict[float, float]:
        """Calculates standard Fibonacci retracement levels."""
        if high == low:
            return {}
        price_range = high - low
        return {
            level: high - (price_range * level)
            for level in [0.236, 0.382, 0.5, 0.618, 0.786]
        }

    def _create_confluence_zones(self, raw_zones: List[Dict], fibo_state: Optional[Dict]) -> List[Dict]:
        """
        Merges raw S/R zones with Fibonacci levels to create high-priority Confluence Zones.
        """
        if not fibo_state or not raw_zones:
            return raw_zones

        high, low = fibo_state['high'], fibo_state['low']
        fib_levels = self._calculate_fib_retracement(high, low)
        
        confluence_zones = []
        used_raw_zones = set()
        CONFLUENCE_THRESHOLD = 0.05  # 5% price proximity for merging

        for fib_level, fib_price in fib_levels.items():
            for i, raw_zone in enumerate(raw_zones):
                if i in used_raw_zones:
                    continue
                
                # Check if a raw zone is close to a fib level
                if abs(raw_zone['price'] - fib_price) / fib_price < CONFLUENCE_THRESHOLD:
                    
                    # Create a new, stronger confluence zone
                    new_zone = raw_zone.copy()
                    new_zone['price'] = (raw_zone['price'] + fib_price) / 2 # Average the price
                    new_zone['type'] = f"confluence_{raw_zone['type']}"
                    new_zone['score'] += 2.0  # Base score bonus for any confluence
                    new_zone['confluence_fib_level'] = fib_level

                    # Extra bonus for "Golden Zone" confluence
                    if fib_level in [0.5, 0.618]:
                        new_zone['score'] += 1.5
                        new_zone['type'] = f"golden_{new_zone['type']}"

                    confluence_zones.append(new_zone)
                    used_raw_zones.add(i)
                    break # Move to the next fib level once a match is found

        # Add any remaining raw zones that didn't form a confluence
        for i, raw_zone in enumerate(raw_zones):
            if i not in used_raw_zones:
                confluence_zones.append(raw_zone)
        
        # Sort by score and return the new, prioritized list of zones
        confluence_zones.sort(key=lambda x: x['score'], reverse=True)
        logger.info(f"Created {len(confluence_zones)} final zones from {len(raw_zones)} raw zones and fib levels.")
        return confluence_zones[:5] # Return top 5 most powerful zones


    async def analyze_token(self, token_data: Dict) -> Tuple[Optional[Dict], Optional[pd.DataFrame]]:
        """
        Main analysis pipeline with the new Confluence Zone generation step.
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
            
            limit_map = {
                ("minute", "1"): 300, ("minute", "5"): 200, ("minute", "15"): 150,
                ("hour", "1"): 200, ("hour", "4"): 150, ("hour", "12"): 100, ("day", "1"): 90
            }
            limit_count = limit_map.get((timeframe, aggregate), 100)
            df = await data_provider.fetch_ohlcv(
                token_data['pool_id'], timeframe=timeframe, aggregate=aggregate, limit=limit_count
            )

            if df is None or df.empty or len(df) < 20:
                return None, None

            fibo_state_dict = None
            async for session in get_db():
                fibo_state = await fibonacci_engine.get_or_create_state(
                    session, token_data['address'], f"{timeframe}_{aggregate}", df
                )
                if fibo_state:
                    fibo_state_dict = {
                        'high': fibo_state.high_point, 'low': fibo_state.low_point,
                        'target1': fibo_state.target1_price, 'target2': fibo_state.target2_price,
                        'target3': fibo_state.target3_price, 'status': fibo_state.status
                    }

            # --- NEW: Generate high-quality Confluence Zones ---
            raw_zones = zone_detector.find_support_resistance_zones(df)
            final_zones = self._create_confluence_zones(raw_zones, fibo_state_dict)
            # --- END NEW ---

            # Pass the FINAL list of zones to the strategy engine
            detected_strategies = await trading_strategies.evaluate_all_strategies(
                df, final_zones, token_data['address']
            )

            if not detected_strategies and token_data.get('volume_24h', 0) > 1000000:
                detected_strategies.append({
                    'signal': 'high_volume', 'strength': min(token_data.get('volume_24h', 0) / 1000000, 10.0)
                })

            if detected_strategies:
                strongest = detected_strategies[0]
                
                holder_stats = token_data.get('holder_stats')
                liquidity_stats = token_data.get('liquidity_stats')
                gem_score = self._calculate_gem_score(strongest, holder_stats, liquidity_stats)
                
                if gem_score < 50:
                    logger.info(f"Skipping {token_data.get('symbol')} - Low gem score: {gem_score:.1f}")
                    return None, None
                
                signal_data = {
                    'token': token_data.get('symbol'), 'address': token_data.get('address'),
                    'pool_id': token_data.get('pool_id'), 'signal_type': strongest.get('signal'),
                    'strength': strongest.get('strength'), 'volume_24h': token_data.get('volume_24h'),
                    'price': token_data.get('price_usd'), 'timeframe': f"{aggregate}{timeframe[0].upper()}",
                    'all_signals': [s.get('signal') for s in detected_strategies], 
                    'zones': final_zones, # Use the final, prioritized zones for charting
                    'gem_score': round(gem_score, 1),
                    'holder_concentration': holder_stats.get('top_10_concentration') if holder_stats else None,
                    'liquidity_flow': liquidity_stats.get('net_flow_24h_usd') if liquidity_stats else None,
                    'fibonacci_state': fibo_state_dict
                }
                return signal_data, df

        except Exception as e:
            logger.error(f"Error analyzing {token_data.get('symbol', 'Unknown')}: {e}", exc_info=True)
        
        return None, None

analysis_engine = AnalysisEngine()
