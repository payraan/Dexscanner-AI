import pandas as pd
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import FibonacciState

# سطوح فیبوناچی برای محاسبه تارگت‌ها
FIB_EXT_LEVELS = {
    'target1': 1.272,
    'target2': 1.618,
    'target3': 2.0
}

class FibonacciEngine:

    async def get_or_create_state(self, session: AsyncSession, token_address: str, timeframe: str, df: pd.DataFrame) -> FibonacciState:
        """
        وضعیت فیبوناچی یک توکن را از دیتابیس می‌خواند یا یک وضعیت جدید ایجاد می‌کند.
        این تابع قلب تپنده سیستم هوشمند فیبوناچی است.
        """
        # 1. جستجو برای یافتن state فعال در دیتابیس
        query = select(FibonacciState).where(
            FibonacciState.token_address == token_address,
            FibonacciState.timeframe == timeframe
        ).order_by(FibonacciState.created_at.desc()).limit(1)

        result = await session.execute(query)
        fibo_state = result.scalar_one_or_none()

        # 2. بررسی و به‌روزرسانی state موجود
        if fibo_state:
            is_valid = await self._validate_and_update_existing_state(session, fibo_state, df)
            if is_valid:
                return fibo_state # اگر state معتبر بود، همان را برمی‌گردانیم

        # 3. اگر state معتبری وجود نداشت، یک state جدید می‌سازیم
        return await self._create_new_state(session, token_address, timeframe, df)

    async def _validate_and_update_existing_state(self, session: AsyncSession, state: FibonacciState, df: pd.DataFrame) -> bool:
        """
        وضعیت فعلی فیبوناچی را بررسی می‌کند. اگر تارگت‌ها زده شده باشند یا نامعتبر شده باشد، آن را آپدیت می‌کند.
        """
        current_price = df['close'].iloc[-1]

        # شرط ابطال: اگر قیمت به زیر کف فیبوناچی سقوط کند
        if current_price < state.low_point:
            state.status = 'INVALIDATED'
            await session.commit()
            return False # state دیگر معتبر نیست

        # شرط تکمیل: اگر قیمت به تارگت نهایی رسیده باشد
        if state.status == 'TARGET_2_HIT' and current_price >= state.target3_price:
            state.status = 'COMPLETED'
            await session.commit()
            return False # state تکمیل شده و باید یک state جدید ساخته شود

        # بررسی رسیدن به تارگت‌ها
        if state.status == 'TARGET_1_HIT' and current_price >= state.target2_price:
            state.status = 'TARGET_2_HIT'
            await session.commit()
        elif state.status == 'ACTIVE' and current_price >= state.target1_price:
            state.status = 'TARGET_1_HIT'
            await session.commit()

        return True # state همچنان معتبر است

    async def _create_new_state(self, session: AsyncSession, token_address: str, timeframe: str, df: pd.DataFrame) -> FibonacciState:
        """
        یک state جدید فیبوناچی بر اساس سقف و کف فعلی قیمت ایجاد می‌کند.
        """
        if df.empty or len(df) < 20:
            return None

        high_point = df['high'].max()
        low_point = df['low'].min()
        price_range = high_point - low_point

        if price_range <= 0:
            return None

        # محاسبه قیمت تارگت‌ها
        target1 = high_point + (price_range * (FIB_EXT_LEVELS['target1'] - 1.0))
        target2 = high_point + (price_range * (FIB_EXT_LEVELS['target2'] - 1.0))
        target3 = high_point + (price_range * (FIB_EXT_LEVELS['target3'] - 1.0))

        # Check if state already exists
        existing = await session.execute(
            select(FibonacciState).where(
                FibonacciState.token_address == token_address,
                FibonacciState.timeframe == timeframe
            )
        )
        if existing.scalar_one_or_none():
            return None

        new_state = FibonacciState(
            token_address=token_address,
            timeframe=timeframe,
            high_point=high_point,
            low_point=low_point,
            target1_price=target1,
            target2_price=target2,
            target3_price=target3,
            status='ACTIVE',
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        session.add(new_state)
        await session.commit()
        return new_state

# یک نمونه از کلاس می‌سازیم تا در همه جا از همین یک نمونه استفاده شود
fibonacci_engine = FibonacciEngine()
