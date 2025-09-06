import asyncio
import logging
from typing import List, Dict

# --- NEW: Import the EventEngine and the Token model ---
from app.database.models import Token, Blacklist
# --- END NEW ---

from app.services.cooldown_service import token_state_service
from app.scanner.data_provider import data_provider
from app.scanner.analysis import analysis_engine
from app.core.config import settings
from app.scanner.telegram_sender import telegram_sender
from app.services.token_service import token_service
from app.scanner.token_health import token_health_checker
from app.services.bitquery_service import bitquery_service
from app.database.session import get_db
from sqlalchemy import select
from sqlalchemy.orm import undefer

from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Scanner configuration
BATCH_SIZE = 5  # تعداد پیام برای ارسال در هر دسته
RATE_LIMIT_DELAY = 1  # تاخیر 1 ثانیه بین هر ارسال
RANGING_THRESHOLD = 5.0  # درصد تغییر برای ورود به حالت ranging
BREAKOUT_THRESHOLD = 7.0  # درصد تغییر برای خروج از ranging
RANGING_TIMEOUT = timedelta(hours=2)  # حداکثر زمان در حالت ranging
MIN_UPDATE_INTERVAL = timedelta(minutes=30)  # حداقل فاصله بین آپدیت‌ها

class TokenScanner:
   def __init__(self):
       self.running = False
       self.scan_count = 0

   async def _monitor_and_process_events(self, tokens_from_api: List[Dict]):
    """
    Monitors tokens and sends updates for all healthy tokens.
    """
    async for session in get_db():
        updates_to_send = []

        # Reset cooldown tokens at the beginning of each monitoring cycle
        await token_state_service.reset_cooled_down_tokens(session)

        for token_data in tokens_from_api:
            # Check if token is blacklisted
            blacklist_check = await session.execute(
                select(Blacklist).where(Blacklist.token_address == token_data['address'])
            )
            if blacklist_check.scalar_one_or_none():
                logger.info(f"⛔ Skipping blacklisted token: {token_data.get('symbol', 'Unknown')}")
                continue

            # Get token record
            token_record_result = await session.execute(
                select(Token).where(Token.address == token_data['address']).options(undefer("*"))
            )
            token = token_record_result.scalar_one_or_none()
            if not token:
                logger.warning(f"Token {token_data['symbol']} not found in DB, skipping.")
                continue

            # EAGERLY LOAD ALL required attributes immediately into local variables
            last_price = token.last_scan_price
            current_state = token.state
            msg_id = token.message_id
            rep_count = token.reply_count

            # Skip tokens in cooldown immediately after loading state
            if current_state in ['SIGNALED', 'COOLDOWN']:
                continue

            current_price = token_data.get('price_usd', 0)
            should_send_update = False

            # First scan logic
            if not last_price:
                should_send_update = True
                token.state = 'WATCHING'
                logger.info(f"🆕 First scan for {token.symbol}")
            else:
                # Calculate price change
                price_change_percent = ((current_price - last_price) / last_price) * 100 if last_price > 0 else 0
                time_since_last_update = datetime.utcnow() - token.last_state_change

                # Ranging logic with time component
                if current_state == 'RANGING':
                    if abs(price_change_percent) > BREAKOUT_THRESHOLD or time_since_last_update > RANGING_TIMEOUT:
                        should_send_update = True
                        if token.state != 'TRENDING':
                            token.state = 'TRENDING'
                            token.last_state_change = datetime.utcnow()
                        logger.info(f"📈 {token.symbol} broke out of range!")
                elif abs(price_change_percent) < RANGING_THRESHOLD:
                    if token.state != 'RANGING':
                        token.state = 'RANGING'
                        logger.info(f"😴 {token.symbol} entered ranging state")
                        token.last_state_change = datetime.utcnow()
                else:  # WATCHING or TRENDING state
                    should_send_update = True
                    if token.state != 'TRENDING':
                        token.state = 'TRENDING'
                        token.last_state_change = datetime.utcnow()

            if should_send_update:
                # Get analysis data
                analysis_data, df = await analysis_engine.analyze_token(token_data, session)
                if analysis_data and df is not None:
                    # Pass the safe local variables, not the lazy-loaded attributes
                    updates_to_send.append((analysis_data, df, token, last_price, current_state, msg_id, rep_count))
                    token.last_scan_price = current_price
                    logger.info(f"📤 Queued update for {token_data.get('symbol', 'Unknown')}")

        # Batch sending with rate limiting
        if updates_to_send:
            logger.info(f"📨 Sending {len(updates_to_send)} updates in batches...")
            for update_args in updates_to_send:
                try:
                    await telegram_sender.send_signal(*update_args, session=session)
                    analysis_data, _, token, _, _, _, _ = update_args
                    await token_state_service.record_signal_sent(
                        analysis_data['address'],
                        analysis_data['price'],
                        session=session
                    )
                    await asyncio.sleep(RATE_LIMIT_DELAY)
                except Exception as e:
                    logger.error(f"Failed to process update for a token, skipping. Error: {e}", exc_info=True)
                    continue

        await session.commit()

   async def start_scanning(self):
       """Main scanning loop - now simplified to an event monitoring loop."""
       self.running = True
       logger.info(f"Event-Driven Scanner started. Scan interval: {settings.SCAN_INTERVAL} seconds")

       while self.running:
           try:
               self.scan_count += 1
               logger.info(f"--- Starting Monitoring Cycle #{self.scan_count} ---")
               
               tokens = await data_provider.fetch_trending_tokens(limit=settings.TRENDING_TOKENS_LIMIT)

               if tokens:
                   # This step remains to keep our token list up-to-date
                   await token_service.store_tokens_with_health(tokens)
                   logger.info(f"Fetched and stored {len(tokens)} tokens.")
                   
                   # The main logic is now here
                   await self._monitor_and_process_events(tokens)
               else:
                   logger.warning("No trending tokens found in this monitoring cycle.")
               
               logger.info(f"--- Monitoring Cycle #{self.scan_count} Completed ---")
               await asyncio.sleep(settings.SCAN_INTERVAL)

           except Exception as e:
               logger.error(f"CRITICAL ERROR in monitoring loop #{self.scan_count}: {e}", exc_info=True)
               await asyncio.sleep(60)

   def stop(self):
       self.running = False
       logger.info("Scanner stopped")

token_scanner = TokenScanner()
