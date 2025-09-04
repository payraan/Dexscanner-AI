import pandas as pd
from datetime import datetime
from sqlalchemy import select, and_
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

        swing_high_point = df['high'].iloc[latest_high_idx]
        swing_low_point = df['low'].iloc[latest_low_idx]

        return swing_high_point, swing_low_point

    async def _create_or_update_state(self, session: AsyncSession, token_address: str, timeframe: str, high: float, low: float, existing_state: FibonacciState = None) -> FibonacciState:
        """یک وضعیت جدید ایجاد یا وضعیت موجود را باطل و وضعیت جدیدی جایگزین می‌کند."""
        
        # اگر وضعیت قبلی وجود داشت، آن را منسوخ کن
        if existing_state:
            existing_state.status = 'SUPERSEDED' # وضعیتی بهتر از "INVALIDATED"

        price_range = high - low
        if price_range <= 0:
            return None

        new_state = FibonacciState(
            token_address=token_address,
            timeframe=timeframe,
            high_point=high,
            low_point=low,
            target1_price=high + (price_range * (FIB_EXT_LEVELS['target1'] - 1.0)),
            target2_price=high + (price_range * (FIB_EXT_LEVELS['target2'] - 1.0)),
            target3_price=high + (price_range * (FIB_EXT_LEVELS['target3'] - 1.0)),
            status='ACTIVE',
        )
        session.add(new_state)
        await session.commit()
        logger.info(f"🔄 Fibonacci state for {token_address} has been updated/created. New Wave: (H: {high}, L: {low})")
        return new_state

    async def get_or_create_state(self, session: AsyncSession, token_address: str, timeframe: str, df: pd.DataFrame) -> FibonacciState:
        """
        موتور اصلی و کاملاً پویای فیبوناچی.
        """
        # ۱. آخرین سقف و کف مهم را از روی چارت فعلی پیدا کن
        current_swing_high, current_swing_low = self._find_latest_swing_points(df)

        if not current_swing_high or not current_swing_low:
            logger.warning(f"Could not determine a valid swing wave for {token_address}.")
            return None

        # ۲. آخرین وضعیت ذخیره شده در دیتابیس را بگیر
        query = select(FibonacciState).where(
            and_(
                FibonacciState.token_address == token_address,
                FibonacciState.timeframe == timeframe
            )
        ).order_by(FibonacciState.created_at.desc()).limit(1)
        result = await session.execute(query)
        latest_db_state = result.scalar_one_or_none()

        # ۳. تصمیم‌گیری اصلی: آیا باید فیبوناچی را آپدیت کنیم؟
        # اگر هیچ وضعیتی در دیتابیس نیست، یا موج قیمت تغییر کرده، یک وضعیت جدید بساز
        if not latest_db_state or \
           abs(latest_db_state.high_point - current_swing_high) > 1e-9 or \
           abs(latest_db_state.low_point - current_swing_low) > 1e-9:
            
            return await self._create_or_update_state(session, token_address, timeframe, current_swing_high, current_swing_low, latest_db_state)

        # ۴. اگر موج قیمت تغییر نکرده، فقط وضعیت تارگت‌ها را آپدیت کن
        current_price = df['close'].iloc[-1]
        
        if latest_db_state.status == 'ACTIVE' and latest_db_state.target1_price and current_price >= latest_db_state.target1_price:
            latest_db_state.status = 'TARGET_1_HIT'
        elif latest_db_state.status == 'TARGET_1_HIT' and latest_db_state.target2_price and current_price >= latest_db_state.target2_price:
            latest_db_state.status = 'TARGET_2_HIT'
        elif latest_db_state.status == 'TARGET_2_HIT' and latest_db_state.target3_price and current_price >= latest_db_state.target3_price:
            latest_db_state.status = 'COMPLETED'
        
        await session.commit()

        return latest_db_state

# یک نمونه از کلاس می‌سازیم تا در همه جا از همین یک نمونه استفاده شود
fibonacci_engine = FibonacciEngine()
