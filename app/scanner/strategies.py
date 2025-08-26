import pandas as pd
import numpy as np
from typing import List, Dict, Optional

class TradingStrategies:
    
    def __init__(self):
        self.min_candles = 20
    
    def volume_surge(self, df: pd.DataFrame, multiplier: float = 3.0) -> Optional[Dict]:
        """Detect sudden volume surge"""
        if len(df) < 10:
            return None
            
        avg_volume = df['volume'].iloc[-10:-1].mean()
        current_volume = df['volume'].iloc[-1]
        
        if current_volume > avg_volume * multiplier:
            return {
                'signal': 'volume_surge',
                'strength': min(current_volume / avg_volume, 10.0),
                'volume_ratio': current_volume / avg_volume
            }
        return None
    
    def momentum_breakout(self, df: pd.DataFrame) -> Optional[Dict]:
        """Detect momentum breakout above resistance"""
        if len(df) < 20:
            return None
            
        # Find recent high (resistance)
        recent_high = df['high'].iloc[-20:].max()
        current_price = df['close'].iloc[-1]
        
        # Check if current price broke above resistance
        if current_price > recent_high * 1.02:  # 2% above recent high
            # Confirm with volume
            avg_volume = df['volume'].iloc[-10:-1].mean()
            current_volume = df['volume'].iloc[-1]
            
            if current_volume > avg_volume * 1.5:  # Volume confirmation
                return {
                    'signal': 'momentum_breakout',
                    'strength': min((current_price / recent_high - 1) * 50, 10.0),
                    'breakout_level': recent_high
                }
        return None
    
    def support_bounce(self, df: pd.DataFrame) -> Optional[Dict]:
        """Detect bounce from support level"""
        if len(df) < 15:
            return None
            
        # Find recent low (support)
        recent_low = df['low'].iloc[-15:].min()
        current_price = df['close'].iloc[-1]
        
        # Check if price is near support and showing bounce
        distance_from_support = (current_price - recent_low) / recent_low
        
        if 0.005 < distance_from_support < 0.05:  # 0.5% to 5% above support
            # Check for reversal candle pattern
            last_candle_green = df['close'].iloc[-1] > df['open'].iloc[-1]
            prev_candle_red = df['close'].iloc[-2] < df['open'].iloc[-2]
            
            if last_candle_green and prev_candle_red:
                return {
                    'signal': 'support_bounce',
                    'strength': min((1 - distance_from_support) * 20, 10.0),
                    'support_level': recent_low
                }
        return None
    
    def obv_uptrend(self, df: pd.DataFrame) -> Optional[Dict]:
        """Detect OBV uptrend confirmation"""
        if len(df) < 20:
            return None
    
        # Calculate OBV (On Balance Volume)
        obv = []
        obv_val = 0
    
        for i in range(len(df)):
            if i == 0:
                obv_val = df['volume'].iloc[i]
            else:
                if df['close'].iloc[i] > df['close'].iloc[i-1]:
                    obv_val += df['volume'].iloc[i]
                elif df['close'].iloc[i] < df['close'].iloc[i-1]:
                    obv_val -= df['volume'].iloc[i]
            obv.append(obv_val)
    
        df_temp = df.copy()
        df_temp['obv'] = obv
    
        # Check for OBV uptrend with price confirmation
        obv_slope = (obv[-1] - obv[-10]) / 10  # OBV slope over 10 periods
        price_making_higher_highs = df['high'].iloc[-1] > df['high'].iloc[-5]
    
        if obv_slope > 0 and price_making_higher_highs:
            strength = min(abs(obv_slope) / max(obv[-10:]) * 100, 10.0)
            return {
                'signal': 'obv_uptrend',
                'strength': strength,
                'obv_slope': obv_slope
            }
        return None

    def three_white_soldiers(self, df: pd.DataFrame) -> Optional[Dict]:
        """Detect Three White Soldiers candlestick pattern"""
        if len(df) < 5:
            return None
    
        # Get last 3 candles
        last_3 = df.tail(3)
    
        # Check for 3 consecutive green candles
        all_green = all(candle['close'] > candle['open'] for _, candle in last_3.iterrows())
    
        if not all_green:
            return None
    
        # Check for ascending highs and closes
        ascending_closes = (
            last_3.iloc[1]['close'] > last_3.iloc[0]['close'] and
            last_3.iloc[2]['close'] > last_3.iloc[1]['close']
        )
    
        ascending_highs = (
            last_3.iloc[1]['high'] > last_3.iloc[0]['high'] and  
            last_3.iloc[2]['high'] > last_3.iloc[1]['high']
        )
    
        # Check for decent body sizes (not just wicks)
        min_body_size = 0.005  # 0.5% minimum body
        strong_bodies = all(
            abs(candle['close'] - candle['open']) / candle['open'] > min_body_size
            for _, candle in last_3.iterrows()
        )
    
        if ascending_closes and ascending_highs and strong_bodies:
            # Calculate strength based on momentum
            total_gain = (last_3.iloc[-1]['close'] - last_3.iloc[0]['open']) / last_3.iloc[0]['open']
            strength = min(total_gain * 200, 10.0)  # Scale to 0-10
        
            return {
                'signal': 'three_white_soldiers',
                'strength': max(strength, 3.0),  # Minimum strength 3 for this pattern
                'total_gain': total_gain
            }
    
        return None

    def evaluate_all_strategies(self, df: pd.DataFrame) -> List[Dict]:
        """Evaluate all trading strategies"""
        strategies = []
        
        # Test each strategy
        volume_result = self.volume_surge(df)
        if volume_result:
            strategies.append(volume_result)
            
        momentum_result = self.momentum_breakout(df)
        if momentum_result:
            strategies.append(momentum_result)
            
        support_result = self.support_bounce(df)
        if support_result:
            strategies.append(support_result)
        
        # Sort by strength
        strategies.sort(key=lambda x: x['strength'], reverse=True)
        return strategies

        obv_result = self.obv_uptrend(df)
        if obv_result:
            strategies.append(obv_result)

        soldiers_result = self.three_white_soldiers(df)
        if soldiers_result:
            strategies.append(soldiers_result)

trading_strategies = TradingStrategies()
