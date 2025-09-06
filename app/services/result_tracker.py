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
from app.services.template_composer import template_composer

logger = logging.getLogger(__name__)

# --- Constants for better management ---
PROFIT_THRESHOLD = 20.0  # 20% success threshold
RUG_PULL_THRESHOLD = -80.0 # -80% drop
TRACKING_EXPIRATION_DAYS = 7
CLEANUP_EXPIRATION_DAYS = 30

# --- NEW: Define tracking statuses ---
STATUS_TRACKING = 'TRACKING'
STATUS_SUCCESS = 'SUCCESS'
STATUS_FAILED = 'FAILED'
STATUS_EXPIRED = 'EXPIRED'

class ResultTracker:
    def __init__(self):
        self.bot = Bot(token=settings.BOT_TOKEN)

    async def track_signals(self):
        """Main job to track active signals' performance."""
        logger.info("📈 Starting result tracking cycle...")
        async for session in get_db():
            # JOIN مستقیم با Token برای دریافت تمام اطلاعات در یک کوئری
            result = await session.execute(
                select(SignalResult, Token)
                .join(Token, Token.address == SignalResult.token_address)
                .where(SignalResult.tracking_status == STATUS_TRACKING)
            )
            tracking_results = result.all()

            for signal, token in tracking_results:
                try:
                    # دیگر نیازی به کوئری جداگانه برای توکن نیست
                    if not token or not token.pool_id:
                        logger.warning(f"Token or pool_id not found for address {signal.token_address}")
                        continue

                    # Fetch the latest price data
                    pool_details = await data_provider.fetch_pool_details(token.pool_id)
                    if not pool_details or 'base_token_price_usd' not in pool_details:
                        continue
                    
                    current_price = float(pool_details['base_token_price_usd'])
                    if current_price == 0:
                        continue

                    profit = ((current_price - signal.signal_price) / signal.signal_price) * 100

                    # --- CORE LOGIC: Continuously update the peak performance ---
                    if current_price > (signal.peak_price or 0):
                        signal.peak_price = current_price
                        signal.peak_profit_percentage = profit
                        logger.info(f"New peak for {signal.token_symbol}: {profit:.2f}% at ${current_price:.8f}")

                    # --- Check for end conditions ---
                    is_successful = signal.peak_profit_percentage >= PROFIT_THRESHOLD
                    is_expired = datetime.utcnow() > signal.created_at + timedelta(days=TRACKING_EXPIRATION_DAYS)
                    is_rugged = profit < RUG_PULL_THRESHOLD
                    
                    if is_successful or is_expired or is_rugged:
                        await self._close_tracking(session, signal, token.pool_id, is_rugged)

                except Exception as e:
                    logger.error(f"Error tracking signal {signal.id}: {e}", exc_info=True)
            
            await session.commit()

    async def _close_tracking(self, session, signal, pool_id, is_rugged):
        """Closes the tracking for a signal, determines final status, and captures chart if successful."""
        signal.closed_at = datetime.utcnow()

        if is_rugged:
            signal.is_rugged = True
            signal.tracking_status = STATUS_FAILED
            logger.warning(f"🚨 Rug pull detected for {signal.token_symbol}! Tracking closed.")
            return

        # Determine final status based on peak performance
        if signal.peak_profit_percentage >= PROFIT_THRESHOLD:
            signal.tracking_status = STATUS_SUCCESS
            logger.info(f"✅ Successful signal captured for {signal.token_symbol} with peak profit of {signal.peak_profit_percentage:.2f}%")
            # Generate and save the "After" chart for successful signals
            await self._capture_after_chart(signal, pool_id)
        else:
            signal.tracking_status = STATUS_FAILED
            logger.info(f"❌ Signal for {signal.token_symbol} failed to meet profit threshold. Peak: {signal.peak_profit_percentage:.2f}%")
            
    async def _capture_after_chart(self, signal, pool_id):
        """Generates composite before/after images and saves file_ids."""
        try:
            df = await data_provider.fetch_ohlcv(pool_id, limit=200)
            if df is None or df.empty:
                return

            signal_data_for_chart = {
                'token': signal.token_symbol,
                'price': signal.peak_price,
                'address': signal.token_address,
                'timeframe': '1H'
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
            
                # Save the main composite as after_chart_file_id
                if 'instagram_post' in composites:
                    signal.after_chart_file_id = composites['instagram_post']
                
                logger.info(f"Generated composite templates for {signal.token_symbol}")

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
