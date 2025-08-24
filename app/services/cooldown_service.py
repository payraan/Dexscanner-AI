from datetime import datetime, timedelta
from typing import Dict, Set
import logging

logger = logging.getLogger(__name__)

class CooldownService:
    def __init__(self):
        self.cooldown_hours = 2
        self.sent_signals: Dict[str, datetime] = {}  # In-memory storage
    
    async def can_send_signal(self, token_address: str, signal_type: str) -> bool:
        """Check if signal can be sent (not in cooldown)"""
        key = f"{token_address}_{signal_type}"
        
        if key in self.sent_signals:
            time_passed = datetime.utcnow() - self.sent_signals[key]
            return time_passed.total_seconds() > (self.cooldown_hours * 3600)
        
        return True
    
    async def record_signal(self, signal_data: dict):
        """Record sent signal"""
        key = f"{signal_data['address']}_{signal_data['signal_type']}"
        self.sent_signals[key] = datetime.utcnow()
        logger.info(f"📝 Recorded signal: {key}")

cooldown_service = CooldownService()
