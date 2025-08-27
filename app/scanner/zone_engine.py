from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models import ZoneState
from datetime import datetime

class ZoneEngine:

    async def get_zone_state(self, session: AsyncSession, token_address: str, zone_price: float) -> ZoneState:
        """
        وضعیت فعلی یک ناحیه قیمتی را از دیتابیس دریافت می‌کند.
        """
        query = select(ZoneState).where(
            and_(
                ZoneState.token_address == token_address,
                # برای جلوگیری از خطای اعشار، قیمت‌ها را با یک تلورانس کوچک مقایسه می‌کنیم
                ZoneState.zone_price.between(zone_price * 0.999, zone_price * 1.001)
            )
        )
        result = await session.execute(query)
        state = result.scalar_one_or_none()
        
        # اگر state وجود نداشت، یک state پیش‌فرض برمی‌گردانیم
        if not state:
            return ZoneState(current_state='IDLE', last_price=0)
            
        return state

    async def update_zone_state(self, session: AsyncSession, token_address: str, zone_price: float, new_state: str, signal_type: str, current_price: float):
        """
        وضعیت یک ناحیه را در دیتابیس آپدیت یا یک رکورد جدید برای آن ایجاد می‌کند (Upsert).
        """
        existing_state = await self.get_zone_state(session, token_address, zone_price)

        if existing_state and existing_state.id is not None:
            # اگر state از قبل وجود دارد، آن را آپدیت کن
            existing_state.current_state = new_state
            existing_state.last_signal_type = signal_type
            existing_state.last_price = current_price
            existing_state.last_signal_time = datetime.utcnow()
            existing_state.updated_at = datetime.utcnow()
        else:
            # اگر state وجود ندارد، یک رکورد جدید بساز
            new_record = ZoneState(
                token_address=token_address,
                zone_price=zone_price,
                current_state=new_state,
                last_signal_type=signal_type,
                last_price=current_price,
                last_signal_time=datetime.utcnow(),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            session.add(new_record)
        
        await session.commit()

# یک نمونه از کلاس می‌سازیم تا در همه جا از همین یک نمونه استفاده شود
zone_engine = ZoneEngine()
