from app.database.session import get_db
from app.database.models import SignalHistory
from sqlalchemy import select
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class CooldownService:
    def __init__(self):
        self.cooldown_hours = 2
    
    async def can_send_signal(self, token_address: str, signal_type: str) -> bool:
        """Check if signal can be sent using database"""
        async for session in get_db():
            result = await session.execute(
                select(SignalHistory).where(
                    SignalHistory.token_address == token_address,
                    SignalHistory.signal_type == signal_type
                ).order_by(SignalHistory.sent_at.desc()).limit(1)
            )
            last_signal = result.scalar_one_or_none()
            
            if last_signal:
                time_passed = datetime.utcnow() - last_signal.sent_at
                return time_passed.total_seconds() > (self.cooldown_hours * 3600)
            
            return True
    
    async def record_signal(self, signal_data: dict):
        """Record sent signal in database"""
        async for session in get_db():
            new_record = SignalHistory(
                token_address=signal_data['address'],
                signal_type=signal_data['signal_type'],
                sent_at=datetime.utcnow(),
                volume_24h=signal_data.get('volume_24h', 0),
                price=signal_data.get('price', 0)
            )
            session.add(new_record)
            await session.commit()
            logger.info(f"📝 Database recorded: {signal_data['address']}_{signal_data['signal_type']}")

cooldown_service = CooldownService()
