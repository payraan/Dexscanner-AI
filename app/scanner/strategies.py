import pandas as pd
from typing import List, Dict, Optional
from app.database.models import Token
from datetime import datetime, timedelta
import pandas as pd

# تعریف آستانه‌ها
APPROACH_THRESHOLD = 0.025 # 2.5%
BREAKOUT_THRESHOLD = 0.01  # 1%
VOLUME_MULTIPLIER = 5.0    # 5x average volume

class EventEngine:
    """
    Detects specific, high-impact trading events based on price action, zones, and volume.
    This engine replaces the previous strategy-based approach.
    """
    
    def detect_events(self, df: pd.DataFrame, final_zones: List[Dict], token: Token) -> List[Dict]:
        """
        The main function to detect all relevant events for a token in its current state.
        """
        if df.empty or len(df) < 10:
            return []

        events = []
        current_price = df['close'].iloc[-1]
        
        # Event 1: Confirmed Breakout of a significant zone
        # This is an actionable, high-priority event.
        breakout_event = self._check_confirmed_breakout(current_price, final_zones, token, df)
        if breakout_event:
            events.append(breakout_event)

        # Event 2: Volume Explosion
        # This event adds context and can increase the score of other events.
        volume_event = self._check_volume_explosion(df)
        if volume_event:
            events.append(volume_event)
            
        # Event 3: Approaching a Golden Zone
        # This is a "heads-up" event, not an immediate signal.
        approach_event = self._check_golden_zone_approach(current_price, final_zones)
        if approach_event:
            events.append(approach_event)

        # Event 4: Significant price surge since the last signal
        # This is for sending updates on successful signals.
        if token.state == "SIGNALED" and token.last_signal_price:
            price_surge_event = self._check_price_surge(current_price, token.last_signal_price)
            if price_surge_event:
                events.append(price_surge_event)

        return events

    def _check_confirmed_breakout(self, current_price: float, zones: List[Dict], token: Token, df: pd.DataFrame) -> Optional[Dict]:
        """
        Checks if the price has broken and CONFIRMED above a resistance zone.
        This is a simplified, more direct version of the previous stateful strategy.
        We check the last 2 candles for confirmation.
        """
        if len(zones) == 0:
            return None
            
        # We only care about the most immediate resistance zone
        resistance_zones = [z for z in zones if 'resistance' in z['type']]
        if not resistance_zones:
            return None
        
        strongest_resistance = resistance_zones[0]
        zone_price = strongest_resistance['price']
        
        # Check if the last two candles have closed above the zone
        last_close = current_price
        prev_close = pd.Series(df['close']).iloc[-2]

        is_breakout = (
            last_close > zone_price * (1 + BREAKOUT_THRESHOLD) and
            prev_close > zone_price
        )

        if is_breakout and token.state == "WATCHING":
            return {
                "event_type": "BREAKOUT_CONFIRMED",
                "strength": strongest_resistance.get('score', 5.0),
                "level": zone_price,
                "details": f"Confirmed breakout above {'golden' if 'golden' in strongest_resistance['type'] else ''} resistance."
            }
        return None

    def _check_volume_explosion(self, df: pd.DataFrame) -> Optional[Dict]:
        """Detects a massive spike in volume."""
        avg_volume = df['volume'].iloc[-20:-2].mean()
        current_volume = df['volume'].iloc[-1]

        if avg_volume > 0 and current_volume > avg_volume * VOLUME_MULTIPLIER:
            return {
                "event_type": "VOLUME_EXPLOSION",
                "strength": min(current_volume / avg_volume, 10.0),
                "details": f"Volume surged to {current_volume / avg_volume:.1f}x the recent average."
            }
        return None
        
    def _check_golden_zone_approach(self, current_price: float, zones: List[Dict]) -> Optional[Dict]:
        """Checks if the price is getting very close to a powerful Golden Zone."""
        golden_zones = [z for z in zones if 'golden' in z['type']]
        if not golden_zones:
            return None
            
        for zone in golden_zones:
            if abs(current_price - zone['price']) / zone['price'] < APPROACH_THRESHOLD:
                return {
                    "event_type": "APPROACHING_GOLDEN_ZONE",
                    "strength": zone.get('score', 0),
                    "level": zone['price'],
                    "details": f"Price is approaching a Golden Zone at ~${zone['price']:.8f}"
                }
        return None
        
    def _check_price_surge(self, current_price: float, last_signal_price: float) -> Optional[Dict]:
        """Checks for a significant profit run after a signal."""
        profit_percentage = ((current_price - last_signal_price) / last_signal_price) * 100
        if profit_percentage > 30.0: # Threshold for a "success update"
            return {
                "event_type": "PRICE_SURGE_CONFIRMED",
                "strength": 8.0, # High strength for updates
                "details": f"Price is up +{profit_percentage:.1f}% since the initial signal."
            }
        return None

# Instantiate the engine
event_engine = EventEngine()
