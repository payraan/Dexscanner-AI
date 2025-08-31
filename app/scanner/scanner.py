import asyncio
import logging
from typing import List, Dict

# --- NEW: Import the EventEngine and the Token model ---
from app.scanner.strategies import event_engine
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

logger = logging.getLogger(__name__)

class TokenScanner:
   def __init__(self):
       self.running = False
       self.scan_count = 0

   async def _monitor_and_process_events(self, tokens_from_api: List[Dict]):
       """
       Monitors tokens for key events and processes them into signals if they are significant.
       """
       async for session in get_db():
           for token_data in tokens_from_api:
               # Check if token is blacklisted
               blacklist_check = await session.execute(
                   select(Blacklist).where(Blacklist.token_address == token_data['address'])
               )
               if blacklist_check.scalar_one_or_none():
                   logger.info(f"⛔ Skipping blacklisted token: {token_data.get('symbol', 'Unknown')}")
                   continue

               # Get the token's current state from our database
               token_record_result = await session.execute(
                   select(Token).where(Token.address == token_data['address'])
               )
               token = token_record_result.scalar_one_or_none()
               if not token:
                   logger.warning(f"Token {token_data['symbol']} not found in DB, skipping event check.")
                   continue

               # --- The new core logic: Check for events instead of running full analysis ---
               
               # We only need to do a deep dive if the token is in a state we care about
               if token.state not in ["WATCHING", "SIGNALED"]:
                   continue
               
               # Fetch fresh price data to check for events
               signal, df = await analysis_engine.analyze_token(token_data)
               if not signal or df is None or df.empty:
                   continue
               
               # DETECT EVENTS
               detected_events = event_engine.detect_events(df, signal.get('zones', []), token)
               
               if not detected_events:
                   continue # No significant event, move to the next token

               logger.info(f"🔥 Events detected for {token.symbol}: {[e['event_type'] for e in detected_events]}")

               # --- Decide if an event is strong enough to become a signal ---
               # For now, we only send a signal for a confirmed breakout.
               main_event = next((e for e in detected_events if e['event_type'] == 'BREAKOUT_CONFIRMED'), None)
               
               if main_event:
                   # An important event was found, now we build the final signal and send it
                   signal['signal_type'] = main_event['event_type']
                   signal['strength'] = main_event['strength']

                   # Fetch on-chain data for final validation
                   try:
                       holder_stats = await bitquery_service.get_holder_stats(token_data['address'])
                       if holder_stats and holder_stats['top_10_concentration'] > 60:
                           logger.warning(f"❌ Skipping {token.symbol} - High concentration: {holder_stats['top_10_concentration']}%")
                           continue
                       
                       # Optional: Get liquidity stats for high-quality signals
                       liquidity_stats = None
                       if holder_stats and holder_stats['top_10_concentration'] < 30:
                           liquidity_stats = await bitquery_service.get_liquidity_stats(token_data['address'])
                   except Exception as e:
                       logger.error(f"Bitquery analysis failed for {token.symbol}: {e}")
                       holder_stats = None
                       liquidity_stats = None
                   
                   # Ensure we have empty dicts if no data
                   if not holder_stats:
                       holder_stats = {}
                   if not liquidity_stats:
                       liquidity_stats = {}

                   # Re-calculate Gem Score with the new event-based strength and on-chain data
                   signal['gem_score'] = analysis_engine._calculate_gem_score(signal, holder_stats, liquidity_stats)

                   if signal['gem_score'] < 50:
                       logger.info(f"Event found for {token.symbol}, but Gem Score ({signal['gem_score']:.1f}) is too low.")
                       continue

                   # Send the signal and update the token's state
                   await telegram_sender.send_signal(signal, df)
                   await token_state_service.record_signal_sent(
                       signal['address'],
                       signal.get('price', 0)
                   )

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
