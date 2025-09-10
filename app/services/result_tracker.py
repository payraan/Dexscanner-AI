import asyncio
import logging
from datetime import datetime, timedelta
from sqlalchemy import select, update
from aiogram import Bot
from aiogram.types import BufferedInputFile

# --- ۱. تمام import های لازم به صورت صحیح و بدون تکرار اینجا قرار دارد ---
from app.core.config import settings
from app.database.session import get_db
from app.database.models import SignalResult, Token, TokenState
from app.scanner.data_provider import data_provider
from app.scanner.chart_generator import chart_generator
from app.services.cooldown_service import token_state_service, STATE_COOLDOWN
from app.services.template_composer import template_composer
from app.scanner.token_health import token_health_checker

logger = logging.getLogger(__name__)

# --- ثابت‌ها ---
PROFIT_THRESHOLD = 20.0
RUG_PULL_THRESHOLD = -80.0
TRACKING_EXPIRATION_DAYS = 7
CLEANUP_EXPIRATION_DAYS = 30
STATUS_TRACKING = 'TRACKING'
STATUS_SUCCESS = 'SUCCESS'
STATUS_FAILED = 'FAILED'
STATUS_EXPIRED = 'EXPIRED'

class ResultTracker:
    def __init__(self):
        self.bot = Bot(token=settings.BOT_TOKEN)

    async def track_signals(self):
        logger.info("📈 Starting result tracking cycle...")
        async for session in get_db():
            await self._process_tracking_signals(session)
            await self._process_locked_signals(session)
            await session.commit()
            logger.info("✅ Result tracking cycle finished.")

    async def _process_tracking_signals(self, session):
        # این تابع سیگنال‌های جدید را برای رسیدن به موفقیت اولیه بررسی می‌کند
        result = await session.execute(
            select(SignalResult, Token)
            .join(Token, Token.address == SignalResult.token_address)
            .where(SignalResult.tracking_status == STATUS_TRACKING)
        )
        tracking_signals = result.all()
        for signal, token in tracking_signals:
            try:
                current_price = await self._get_current_price(token.pool_id)
                if current_price is None: continue
                profit = ((current_price - signal.signal_price) / signal.signal_price) * 100
                if current_price > (signal.peak_price or 0):
                    signal.peak_price = current_price
                    signal.peak_profit_percentage = profit
                
                is_successful = (signal.peak_profit_percentage or 0) >= PROFIT_THRESHOLD
                is_expired = datetime.utcnow() > signal.created_at + timedelta(days=TRACKING_EXPIRATION_DAYS)
                is_rugged = profit < RUG_PULL_THRESHOLD

                if is_successful:
                    logger.info(f"✅ SUCCESS: {signal.token_symbol} reached {profit:.2f}%. Locking token.")
                    await token_state_service.lock_successful_token(token.address, session)
                    await self._close_tracking(session, signal, token.pool_id, status=STATUS_SUCCESS)
                elif is_expired or is_rugged:
                    status = STATUS_EXPIRED if is_expired else STATUS_FAILED
                    logger.warning(f"❌ FAILED: {signal.token_symbol} closing with status {status}.")
                    await self._close_tracking(session, signal, token.pool_id, status=status)
            except Exception as e:
                logger.error(f"Error in _process_tracking_signals for signal {signal.id}: {e}", exc_info=True)

    async def _process_locked_signals(self, session):
        # این تابع فقط سیگنال‌های موفق را برای آپدیت کردن قله سود بررسی می‌کند
        result = await session.execute(
            select(SignalResult, Token)
            .join(Token, Token.address == SignalResult.token_address)
            .where(
                SignalResult.tracking_status == STATUS_SUCCESS,
                Token.state == TokenState.SUCCESS_LOCKED
            )
        )
        locked_signals = result.all()
        for signal, token in locked_signals:
            try:
                current_price = await self._get_current_price(token.pool_id)
                if current_price is None: continue

                if current_price > (signal.peak_price or 0):
                    old_peak_profit = signal.peak_profit_percentage
                    profit = ((current_price - signal.signal_price) / signal.signal_price) * 100
                    signal.peak_price = current_price
                    signal.peak_profit_percentage = profit
                    logger.info(f"🚀 PEAK UPDATE for {signal.token_symbol}: {old_peak_profit:.2f}% -> {profit:.2f}%")
                    # اگر بخواهید با هر قله جدید چارت هم آپدیت شود، کد آن را اینجا فراخوانی کنید
                    # await self._capture_after_chart(signal, token.pool_id)

                peak_price = signal.peak_price or current_price
                if current_price < peak_price * 0.6: # 40% drop from peak
                    logger.info(f"🔓 UNLOCKING {signal.token_symbol} due to significant price drop.")
                    stmt = (
                        update(Token)
                        .where(Token.address == token.address)
                        .values(state=STATE_COOLDOWN, last_state_change=datetime.utcnow())
                    )
                    await session.execute(stmt)
            except Exception as e:
                logger.error(f"Error in _process_locked_signals for signal {signal.id}: {e}", exc_info=True)

    # --- ۲. نسخه صحیح و ساده شده تابع _close_tracking ---
    async def _close_tracking(self, session, signal: SignalResult, pool_id: str, status: str):
        signal.closed_at = datetime.utcnow()
        signal.tracking_status = status
        
        if status == STATUS_SUCCESS:
            logger.info(f"✅ Capturing final chart for successful signal: {signal.token_symbol}")
            await self._capture_after_chart(signal, pool_id)
        
        session.add(signal)
        logger.info(f"Tracking closed for {signal.token_symbol} with status: {status}")

    async def _get_current_price(self, pool_id: str):
        try:
            pool_details = await data_provider.fetch_pool_details(pool_id)
            if pool_details and 'base_token_price_usd' in pool_details:
                price = float(pool_details['base_token_price_usd'])
                return price if price > 0 else None
        except Exception as e:
            logger.error(f"Could not fetch price for pool {pool_id}: {e}")
        return None

    async def _capture_after_chart(self, signal, pool_id):
        """Generates composite before/after images and saves file_ids."""
        try:
            # استخراج تایم‌فریم از سیگنال ذخیره شده
            timeframe_str = signal.initial_timeframe or "1H"
            
            # تبدیل فرمت: '5M' -> timeframe='minute', aggregate='5'
            import re
            match = re.match(r'(\d+)([MHD])', timeframe_str)
            if match:
                aggregate = match.group(1)
                unit = match.group(2)
                timeframe_map = {'M': 'minute', 'H': 'hour', 'D': 'day'}
                timeframe = timeframe_map.get(unit, 'hour')
            else:
                timeframe = 'hour'
                aggregate = '1'
            
            # دریافت داده‌ها با تایم‌فریم صحیح
            df = await data_provider.fetch_ohlcv(pool_id, timeframe=timeframe, aggregate=aggregate, limit=200)
            if df is None or df.empty:
                logger.warning(f"No data available for {signal.token_symbol} in timeframe {timeframe_str}")
                return

            signal_data_for_chart = {
                'token': signal.token_symbol,
                'price': signal.peak_price,
                'address': signal.token_address,
                'timeframe': timeframe_str  # استفاده از تایم‌فریم اصلی
            }
            after_chart_bytes = chart_generator.create_signal_chart(df, signal_data_for_chart)

            if after_chart_bytes and signal.before_chart_file_id:
                # Download before chart
                before_chart_response = await self.bot.get_file(signal.before_chart_file_id)
                before_chart_bytes_stream = await self.bot.download_file(before_chart_response.file_path)
                
                # Read the content only ONCE and store it
                before_chart_content = before_chart_bytes_stream.read()

                # Create composite images for different platforms
                composites = {}
                templates = ['instagram_post', 'instagram_story', 'social_wide']
            
                for template_type in templates:
                    composite_bytes = template_composer.create_composite(
                        before_chart_content,  # Use the stored content
                        after_chart_bytes,
                        signal.token_symbol,
                        signal.peak_profit_percentage,
                        template_type
                    )
                
                    if composite_bytes:
                        photo = BufferedInputFile(composite_bytes, filename=f"{template_type}_{signal.token_symbol}.png")
                        sent_message = await self.bot.send_photo(
                            chat_id=settings.ADMIN_CHANNEL_ID,
                            photo=photo,
                            caption=f"📈 {template_type.replace('_', ' ').title()} - {signal.token_symbol}\nProfit: +{signal.peak_profit_percentage:.2f}%"
                        )
                        composites[template_type] = sent_message.photo[-1].file_id
            
                # Save the entire dictionary of file_ids to the new JSONB column
                signal.composite_file_ids = composites
                
                logger.info(f"Generated composite templates for {signal.token_symbol} with timeframe {timeframe_str}")

        except Exception as e:
            logger.error(f"Failed to generate composite for {signal.token_symbol}: {e}", exc_info=True)

    async def cleanup_old_results(self):
        """Cleans up results that are no longer being tracked."""
        logger.info("🧹 Running old results cleanup job...")
        async for session in get_db():
            from sqlalchemy import delete
            # Delete results that are closed and older than the cleanup period
            await session.execute(
                delete(SignalResult).where(
                    SignalResult.tracking_status.in_([STATUS_SUCCESS, STATUS_FAILED, STATUS_EXPIRED]),
                    SignalResult.closed_at < datetime.utcnow() - timedelta(days=CLEANUP_EXPIRATION_DAYS)
                )
            )
            await session.commit()

# --- Async loops (remain unchanged) ---

result_tracker = ResultTracker()

async def run_tracking_loop():
    """Endless loop to run the signal tracker."""
    while True:
        try:
            await result_tracker.track_signals()
        except Exception as e:
            logger.error(f"Critical error in tracking loop: {e}", exc_info=True)
        await asyncio.sleep(30 * 60)  # Every 30 minutes

async def run_cleanup_loop():
    """Endless loop to run the old results cleanup."""
    while True:
        try:
            await result_tracker.cleanup_old_results()
        except Exception as e:
            logger.error(f"Critical error in cleanup loop: {e}", exc_info=True)
        await asyncio.sleep(24 * 60 * 60)  # Every 24 hours
