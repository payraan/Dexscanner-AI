import asyncio
import logging
from typing import List, Dict
from app.scanner.data_provider import data_provider
from app.scanner.analysis import analysis_engine
from app.core.config import settings
from app.scanner.telegram_sender import telegram_sender
from app.services.cooldown_service import cooldown_service
from app.services.token_service import token_service
from app.scanner.token_health import token_health_checker

logger = logging.getLogger(__name__)

class TokenScanner:
   def __init__(self):
       self.running = False
       self.scan_count = 0

   async def _analyze_and_send_signals(self, tokens: List[Dict]):
       """Analyze tokens, check health, check cooldown, and send valid signals."""
       
       signals_to_send = []
       healthy_tokens = 0
       
       # Analyze all tokens
       for token in tokens:
           # First check token health
           df_for_health = await data_provider.fetch_ohlcv(
               token['pool_id'],
               timeframe="hour",
               aggregate="1", 
               limit=50
           )
           
           health_status = await token_health_checker.check_token_health(df_for_health, token)
           
           # Skip rugged or suspicious tokens
           if health_status in ['rugged', 'suspicious']:
               logger.warning(f"❌ Skipping {token['symbol']}: {health_status}")
               continue
               
           healthy_tokens += 1
           
           # Get signal and DataFrame from analysis_engine
           signal, df = await analysis_engine.analyze_token(token)
           
           if signal and df is not None and not df.empty:
               can_send = await cooldown_service.can_send_signal(
                   signal['address'],
                   signal['signal_type']
               )
               
               if can_send:
                   # Add health status to signal data
                   signal['health_status'] = health_status
                   signals_to_send.append((signal, df))
                   logger.info(f"📈 Signal Queued: {signal['token']} - {signal['signal_type']}")
               else:
                   logger.info(f"🔵 Cooldown: {signal['token']} - skipped")

       logger.info(f"🏥 Health Check: {healthy_tokens}/{len(tokens)} tokens passed health screening")

       if not signals_to_send:
           logger.info("⚪ No new signals to send.")
           return

       logger.info(f"🚨 Preparing to send {len(signals_to_send)} signals...")
       
       # Send all valid signals
       for signal, df in signals_to_send:
           await telegram_sender.send_signal(signal, df)
           await cooldown_service.record_signal(signal)

   async def start_scanning(self):
       """Start background scanning loop"""
       self.running = True
       logger.info(f"🚀 Scanner started (interval: {settings.SCAN_INTERVAL}s)")

       while self.running:
           try:
               self.scan_count += 1
               logger.info(f"🔍 Starting scan #{self.scan_count}")
               
               tokens = await data_provider.fetch_trending_tokens(
                   limit=settings.TRENDING_TOKENS_LIMIT
               )

               if tokens:
                   # Store tokens in database with health status
                   await token_service.store_tokens_with_health(tokens)
                   logger.info(f"📊 Found {len(tokens)} trending tokens. Stored and analyzing...")
                   await self._analyze_and_send_signals(tokens)
               else:
                   logger.warning("⚠️ No trending tokens found in this scan cycle.")
               
               logger.info(f"✅ Scan #{self.scan_count} completed.")
               await asyncio.sleep(settings.SCAN_INTERVAL)

           except Exception as e:
               logger.error(f"❌ An error in scanner loop: {e}", exc_info=True)
               await asyncio.sleep(60)

   def stop(self):
       """Stop scanning"""
       self.running = False

token_scanner = TokenScanner()
