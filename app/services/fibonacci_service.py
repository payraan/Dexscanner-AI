from app.database.session import get_db
from app.database.models import FibonacciState
from sqlalchemy import select
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class FibonacciService:
    async def get_or_create_fibonacci_state(self, token_address: str, timeframe: str, df):
        """
        منطق هوشمند فیبوناچی - مشابه ربات قدیمی
        """
        async for session in get_db():
            # بررسی وجود state فعال
            result = await session.execute(
                select(FibonacciState).where(
                    FibonacciState.token_address == token_address,
                    FibonacciState.timeframe == timeframe,
                    FibonacciState.status.in_(['ACTIVE', 'TARGET_1_HIT', 'TARGET_2_HIT'])
                )
            )
            fibo_state = result.scalar_one_or_none()
            
            current_price = df['close'].iloc[-1]
            
            if fibo_state:
                # بررسی invalidation (افت 3% زیر کف)
                if current_price < fibo_state.low_point * 0.97:
                    fibo_state.status = 'INVALIDATED'
                    await session.commit()
                    fibo_state = None
                    
                # بررسی تارگت‌ها
                elif fibo_state.status == 'ACTIVE' and current_price > fibo_state.target1_price:
                    fibo_state.status = 'TARGET_1_HIT'
                    await session.commit()
                    logger.info(f"🎯 Target 1.272 hit for {token_address}")
                    
                elif fibo_state.status == 'TARGET_1_HIT' and current_price > fibo_state.target2_price:
                    fibo_state.status = 'TARGET_2_HIT'
                    await session.commit()
                    logger.info(f"🎯 Target 1.618 hit for {token_address}")
                    
                elif fibo_state.status == 'TARGET_2_HIT' and current_price > fibo_state.target3_price:
                    fibo_state.status = 'COMPLETED'
                    await session.commit()
                    logger.info(f"🎯 Target 2.0 hit - Resetting fibonacci for {token_address}")
                    fibo_state = None
            
            # ایجاد state جدید در صورت نیاز
            if not fibo_state:
                high_point = df['high'].max()
                low_point = df['low'].min()
                price_range = high_point - low_point
                
                if price_range > 0:
                    new_state = FibonacciState(
                        token_address=token_address,
                        timeframe=timeframe,
                        high_point=float(high_point),
                        low_point=float(low_point),
                        target1_price=float(high_point + (price_range * 0.272)),
                        target2_price=float(high_point + (price_range * 0.618)),
                        target3_price=float(high_point + (price_range * 1.0)),
                        status='ACTIVE'
                    )
                    session.add(new_state)
                    await session.commit()
                    logger.info(f"📐 New fibonacci state created for {token_address}")
                    return new_state
            
            return fibo_state

fibonacci_service = FibonacciService()
