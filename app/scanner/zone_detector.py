import pandas as pd
import numpy as np
from scipy.signal import argrelextrema
from typing import List, Dict, Optional

class ZoneDetector:
    def __init__(self):
        self.min_zone_score = 2.0
        self.max_zones = 5
    
    def find_support_resistance_zones(self, df: pd.DataFrame) -> List[Dict]:
        """Find support and resistance zones using swing points"""
        if len(df) < 20:
            return []
        
        zones = []
        
        # Find swing highs and lows
        order = 5  # Look for peaks/valleys over 5 periods
        high_points = argrelextrema(df['high'].values, np.greater, order=order)[0]
        low_points = argrelextrema(df['low'].values, np.less, order=order)[0]
        
        # Process resistance zones (from swing highs)
        for idx in high_points[-10:]:  # Only recent highs
            if idx < 5 or idx > len(df) - 5:
                continue
                
            level_price = df['high'].iloc[idx]
            touches = self._count_touches(df, level_price, 'resistance')
            
            if touches >= 2:
                score = self._calculate_zone_score(df, idx, level_price, 'resistance')
                if score >= self.min_zone_score:
                    zones.append({
                        'type': 'resistance',
                        'price': level_price,
                        'score': score,
                        'touches': touches
                    })
        
        # Process support zones (from swing lows)
        for idx in low_points[-10:]:  # Only recent lows
            if idx < 5 or idx > len(df) - 5:
                continue
                
            level_price = df['low'].iloc[idx]
            touches = self._count_touches(df, level_price, 'support')
            
            if touches >= 2:
                score = self._calculate_zone_score(df, idx, level_price, 'support')
                if score >= self.min_zone_score:
                    zones.append({
                        'type': 'support',
                        'price': level_price,
                        'score': score,
                        'touches': touches
                    })
        
        # Sort by score and return top zones
        zones.sort(key=lambda x: x['score'], reverse=True)
        return zones[:self.max_zones]
    
    def _count_touches(self, df: pd.DataFrame, level: float, zone_type: str) -> int:
        """Count how many times price touched a level"""
        tolerance = level * 0.01  # 1% tolerance
        touches = 0
        
        if zone_type == 'resistance':
            for high in df['high']:
                if abs(high - level) <= tolerance:
                    touches += 1
        else:  # support
            for low in df['low']:
                if abs(low - level) <= tolerance:
                    touches += 1
                    
        return touches
    
    def _calculate_zone_score(self, df: pd.DataFrame, idx: int, level: float, zone_type: str) -> float:
        """Calculate zone strength score"""
        touches = self._count_touches(df, level, zone_type)
        
        # Base score from touches
        score = touches * 1.0
        
        # Volume bonus
        if idx < len(df):
            avg_volume = df['volume'].mean()
            current_volume = df['volume'].iloc[idx]
            if current_volume > avg_volume:
                score += (current_volume / avg_volume) * 0.5
        
        # Recency bonus (more recent = higher score)
        recency_factor = idx / len(df)
        score += recency_factor * 1.0
        
        return min(score, 10.0)  # Cap at 10

zone_detector = ZoneDetector()
