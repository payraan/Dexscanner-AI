import pandas as pd
from datetime import datetime
from sqlalchemy import select, and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models import FibonacciState
from scipy.signal import argrelextrema
import numpy as np
import logging

logger = logging.getLogger(__name__)

# سطوح فیبوناچی برای محاسبه تارگت‌ها
FIB_EXT_LEVELS = {
    'target1': 1.272,
    'target2': 1.618,
    'target3': 2.0
}

class FibonacciEngine:

    def _find_latest_swing_points(self, df: pd.DataFrame):
        """
        آخرین موج حرکتی معتبر (آخرین سقف و کف مهم) را با استفاده از الگوریتم شناسایی می‌کند.
        """
        if len(df) < 20:
            return None, None

        # پیدا کردن نقاط اکسترمم نسبی (قلّه‌ها و دره‌ها)
        swing_high_indices = argrelextrema(df['high'].values, np.greater_equal, order=5)[0]
        swing_low_indices = argrelextrema(df['low'].values, np.less_equal, order=5)[0]

        if swing_high_indices.size == 0 or swing_low_indices.size == 0:
            return None, None

        # آخرین سقف و کف مهم را پیدا کن
        latest_high_idx = swing_high_indices[-1]
        
        # پیدا کردن آخرین کف مهمی که قبل از آخرین سقف رخ داده است
        relevant_low_indices = swing_low_indices[swing_low_indices < latest_high_idx]
        if relevant_low_indices.size == 0:
            return None, None # موج معتبری پیدا نشد
        
        latest_low_idx = relevant_low_indices[-1]

        # FIX: استخراج درست swing points
        swing_high_point = df['high'].iloc[latest_high_idx]
        swing_low_point = df['low'].iloc[latest_low_idx]

        return swing_high_point, swing_low_point

    async def get_or_create_state(self, session: AsyncSession, token_address: str, timeframe: str, df: pd.DataFrame) -> FibonacciState:
        """
        موتور اصلی فیبوناچی با PostgreSQL UPSERT pattern
        """
        try:
            current_swing_high, current_swing_low = self._find_latest_swing_points(df)
            current_price = df['close'].iloc[-1]

            # اگر موج معتبری پیدا نشد، state موجود را برگردان (در صورت وجود)
            if not current_swing_high or not current_swing_low:
                query = select(FibonacciState).where(
                    and_(
                        FibonacciState.token_address == token_address,
                        FibonacciState.timeframe == timeframe
                    )
                )
                result = await session.execute(query)
                existing_state = result.scalar_one_or_none()
                
                if existing_state:
                    # حتی اگر موج جدید نداشتیم، status را بر اساس قیمت فعلی آپدیت کن
                    self._update_status_based_on_price(existing_state, current_price)
                    await session.commit()
                
                return existing_state

            # محاسبه تارگت‌ها
            price_range = current_swing_high - current_swing_low
            if price_range <= 0:
                logger.warning(f"Invalid price range for {token_address}: {price_range}")
                return None

            target1_price = current_swing_high + (price_range * (FIB_EXT_LEVELS['target1'] - 1.0))
            target2_price = current_swing_high + (price_range * (FIB_EXT_LEVELS['target2'] - 1.0))
            target3_price = current_swing_high + (price_range * (FIB_EXT_LEVELS['target3'] - 1.0))

            # تعیین status بر اساس قیمت فعلی
            if current_price >= target3_price:
                status = 'COMPLETED'
            elif current_price >= target2_price:
                status = 'TARGET_2_HIT'
            elif current_price >= target1_price:
                status = 'TARGET_1_HIT'
            else:
                status = 'ACTIVE'

            # PostgreSQL UPSERT using ON CONFLICT
            # ابتدا سعی می‌کنیم رکورد جدید بسازیم
            new_state = FibonacciState(
                token_address=token_address,
                timeframe=timeframe,
                high_point=float(current_swing_high),
                low_point=float(current_swing_low),
                target1_price=float(target1_price),
                target2_price=float(target2_price),
                target3_price=float(target3_price),
                status=status,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )

            try:
                session.add(new_state)
                await session.commit()
                logger.info(f"Created new Fibonacci state for {token_address}")
                return new_state

            except IntegrityError:
                # رکورد از قبل وجود دارد، آن را آپدیت کن
                await session.rollback()
                
                # رکورد موجود را پیدا کن
                query = select(FibonacciState).where(
                    and_(
                        FibonacciState.token_address == token_address,
                        FibonacciState.timeframe == timeframe
                    )
                )
                result = await session.execute(query)
                existing_state = result.scalar_one_or_none()

                if existing_state:
                    # فقط در صورت تغییر موج، آپدیت کن
                    wave_changed = (
                        abs(existing_state.high_point - current_swing_high) > 1e-9 or
                        abs(existing_state.low_point - current_swing_low) > 1e-9
                    )
                    
                    if wave_changed:
                        existing_state.high_point = float(current_swing_high)
                        existing_state.low_point = float(current_swing_low)
                        existing_state.target1_price = float(target1_price)
                        existing_state.target2_price = float(target2_price)
                        existing_state.target3_price = float(target3_price)
                        existing_state.updated_at = datetime.utcnow()
                        logger.info(f"Updated Fibonacci wave for {token_address}")
                    
                    # همیشه status را آپدیت کن
                    if existing_state.status != status:
                        existing_state.status = status
                        existing_state.updated_at = datetime.utcnow()
                    
                    await session.commit()
                    return existing_state
                else:
                    logger.error(f"Race condition: could not find or create state for {token_address}")
                    return None

        except Exception as e:
            logger.error(f"Unexpected error in get_or_create_state for {token_address}: {e}", exc_info=True)
            await session.rollback()
            return None

    def _update_status_based_on_price(self, state: FibonacciState, current_price: float):
        """
        Status را بر اساس قیمت فعلی به‌روزرسانی می‌کند
        """
        new_status = None
        
        if state.target3_price and current_price >= state.target3_price:
            new_status = 'COMPLETED'
        elif state.target2_price and current_price >= state.target2_price:
            new_status = 'TARGET_2_HIT'
        elif state.target1_price and current_price >= state.target1_price:
            new_status = 'TARGET_1_HIT'
        else:
            new_status = 'ACTIVE'
        
        if state.status != new_status:
            state.status = new_status
            state.updated_at = datetime.utcnow()

# یک نمونه از کلاس می‌سازیم تا در همه جا از همین یک نمونه استفاده شود
fibonacci_engine = FibonacciEngine()
