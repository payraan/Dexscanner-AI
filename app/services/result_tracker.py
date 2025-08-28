import asyncio
import logging
from datetime import datetime, timedelta
from sqlalchemy import select
from app.database.session import get_db
from app.database.models import SignalResult, Token
from app.scanner.data_provider import data_provider
from app.scanner.chart_generator import chart_generator
from app.core.config import settings
from aiogram import Bot
from aiogram.types import BufferedInputFile

logger = logging.getLogger(__name__)

# --- ثابت‌ها برای مدیریت بهتر ---
PROFIT_THRESHOLD = 20.0  # 20%
RUG_PULL_THRESHOLD = -80.0  # -80%
TRACKING_EXPIRATION_DAYS = 7
CLEANUP_EXPIRATION_DAYS = 30

class ResultTracker:
    def __init__(self):
        """سازنده کلاس که فقط یک نمونه از Bot را برای ارسال پیام نگه می‌دارد."""
        self.bot = Bot(token=settings.BOT_TOKEN)

    async def track_signals(self):
        """Job اصلی برای ردیابی سیگنال‌های فعال (متد در سطح کلاس)."""
        logger.info("Starting result tracking cycle...")
        async for session in get_db():
            result = await session.execute(
                select(SignalResult).where(SignalResult.status == 'TRACKING')
            )
            tracking_signals = result.scalars().all()

            for signal in tracking_signals:
                try:
                    # بررسی انقضای ردیابی
                    if datetime.utcnow() > signal.created_at + timedelta(days=TRACKING_EXPIRATION_DAYS):
                        signal.status = 'EXPIRED'
                        logger.info(f"Tracking expired for {signal.token_symbol}")
                        continue

                    # دریافت pool_id از جدول Token
                    token_result = await session.execute(
                        select(Token).where(Token.address == signal.token_address)
                    )
                    token = token_result.scalar_one_or_none()
                    if not token or not token.pool_id:
                        logger.warning(f"Token or pool_id not found for address {signal.token_address}")
                        continue

                    # دریافت داده‌های جدید
                    pool_details = await data_provider.fetch_pool_details(token.pool_id)
                    if not pool_details:
                        continue

                    current_price = float(pool_details.get('base_token_price_usd', 0))
                    if current_price == 0:
                        continue

                    profit = ((current_price - signal.signal_price) / signal.signal_price) * 100

                    # بروزرسانی بالاترین قیمت
                    if current_price > (signal.peak_price or 0):
                        signal.peak_price = current_price
                        signal.profit_percentage = profit

                    # بررسی شرایط راگ پول
                    if profit < RUG_PULL_THRESHOLD:
                        signal.is_rugged = True
                        signal.status = 'EXPIRED'
                        logger.warning(f"Rug pull detected for {signal.token_symbol}")
                        continue

                    # بررسی رسیدن به سود (فقط یک بار ثبت می‌شود)
                    if profit >= PROFIT_THRESHOLD and signal.status == 'TRACKING':
                        await self.capture_successful_result(session, signal, token.pool_id, current_price)

                except Exception as e:
                    logger.error(f"Error tracking signal {signal.id}: {e}", exc_info=True)
            
            await session.commit()

    async def capture_successful_result(self, session, signal, pool_id, current_price):
        """یک نتیجه موفق را ثبت و چارت After را تولید می‌کند (متد در سطح کلاس)."""
        logger.info(f"Capturing successful result for {signal.token_symbol} with {signal.profit_percentage:.2f}% profit")
        try:
            # دریافت داده‌های کندل برای چارت جدید
            df = await data_provider.fetch_ohlcv(pool_id, limit=200)
            if df is None or df.empty:
                return

            # ساخت چارت After
            signal_data_for_chart = {
                'token': signal.token_symbol,
                'price': current_price,
                'address': signal.token_address,
                'timeframe': '1H' # یک تایم فریم پیش فرض برای نمایش
            }
            chart_bytes = chart_generator.create_signal_chart(df, signal_data_for_chart)

            if chart_bytes:
                photo = BufferedInputFile(chart_bytes, filename="after.png")
                
                # ارسال به کانال ادمین برای دریافت file_id
                sent_message = await self.bot.send_photo(
                    chat_id=settings.ADMIN_CHANNEL_ID,
                    photo=photo,
                    caption=f"After Chart - {signal.token_symbol} - Profit: {signal.profit_percentage:.2f}%"
                )
                signal.after_chart_file_id = sent_message.photo[-1].file_id
                signal.status = 'CAPTURED'
                signal.captured_at = datetime.utcnow()
                logger.info(f"Successfully captured result for {signal.token_symbol}")

        except Exception as e:
            logger.error(f"Failed to capture result for {signal.token_symbol}: {e}", exc_info=True)

    async def cleanup_old_results(self):
        """نتایج ثبت شده قدیمی‌تر از حد معین را پاکسازی می‌کند (متد در سطح کلاس)."""
        logger.info("Running old results cleanup job...")
        async for session in get_db():
            from sqlalchemy import delete
            # فقط نتایجی که ثبت شده (captured) و قدیمی هستند حذف شوند
            await session.execute(
                delete(SignalResult).where(
                    SignalResult.status == 'CAPTURED',
                    SignalResult.captured_at < datetime.utcnow() - timedelta(days=CLEANUP_EXPIRATION_DAYS)
                )
            )
            await session.commit()

# --- نمونه‌سازی و حلقه‌های اجرایی ---

result_tracker = ResultTracker()

async def run_tracking_loop():
    """حلقه بی‌پایان برای اجرای ردیاب سیگنال‌ها."""
    while True:
        try:
            await result_tracker.track_signals()
        except Exception as e:
            logger.error(f"Critical error in tracking loop: {e}", exc_info=True)
        await asyncio.sleep(30 * 60)  # هر 30 دقیقه

async def run_cleanup_loop():
    """حلقه بی‌پایان برای اجرای پاکسازی نتایج قدیمی."""
    while True:
        try:
            await result_tracker.cleanup_old_results()
        except Exception as e:
            logger.error(f"Critical error in cleanup loop: {e}", exc_info=True)
        await asyncio.sleep(24 * 60 * 60)  # هر 24 ساعت
