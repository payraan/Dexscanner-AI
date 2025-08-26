import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

class TokenHealthChecker:
    def __init__(self):
        self.MAX_ATH_DROP = 0.90  # حداکثر افت 90% از سقف
        self.MIN_VOLUME_HEALTH = 50000  # حداقل حجم برای سلامت
        
    async def check_token_health(self, df: pd.DataFrame, token_data: Dict) -> str:
        """
        Check if token is healthy, rugged, or suspicious
        Returns: 'active', 'rugged', 'suspicious', 'unknown'
        """
        if df is None or df.empty or len(df) < 5:
            return 'unknown'
            
        try:
            ath = df['high'].max()
            current_price = df['close'].iloc[-1]
            volume_24h = token_data.get('volume_24h', 0)
            
            # Check for rug pull (massive drop from ATH)
            if ath > 0:
                drop_ratio = (ath - current_price) / ath
                if drop_ratio > self.MAX_ATH_DROP:
                    logger.warning(f"🔥 Potential RUG detected: {token_data['symbol']} - {drop_ratio:.1%} drop from ATH")
                    return 'rugged'
            
            # Check volume health
            if volume_24h < self.MIN_VOLUME_HEALTH:
                return 'suspicious'
                
            # Check for dead token (flat price action)
            price_variance = df['close'].std()
            if price_variance < current_price * 0.001:  # Less than 0.1% price variance
                return 'suspicious'
                
            return 'active'
            
        except Exception as e:
            logger.error(f"Health check error for {token_data.get('symbol', 'Unknown')}: {e}")
            return 'unknown'

token_health_checker = TokenHealthChecker()
