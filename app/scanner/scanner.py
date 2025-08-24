import asyncio
import logging
from typing import List, Dict
from app.scanner.data_provider import data_provider
from app.scanner.analysis import analysis_engine
from app.core.config import settings
from app.scanner.telegram_sender import telegram_sender
from app.services.cooldown_service import cooldown_service

logger = logging.getLogger(__name__)

class TokenScanner:
    def __init__(self):
        self.running = False
        self.scan_count = 0

    async def _analyze_and_send_signals(self, tokens: List[Dict]):
        """Analyze tokens, check cooldown, and send valid signals."""
        
        signals_to_send = []
        
        # Analyze all tokens
        for token in tokens:
            # دریافت هم signal و هم DataFrame از analysis_engine
            signal, df = await analysis_engine.analyze_token(token)
            
            if signal and df is not None and not df.empty:
                can_send = await cooldown_service.can_send_signal(
                    signal['address'], 
                    signal['signal_type']
                )
                
                if can_send:
                    # سیگنال و DataFrame را با هم برای ارسال آماده می‌کنیم
                    signals_to_send.append((signal, df))
                    logger.info(f"📈 Signal Queued: {signal['token']} - {signal['signal_type']}")
                else:
                    logger.info(f"🔵 Cooldown: {signal['token']} - skipped")

        if not signals_to_send:
            logger.info("⚪ No new signals to send.")
            return

        logger.info(f"🚨 Preparing to send {len(signals_to_send)} signals...")
        
        # ارسال تمام سیگنال‌های معتبر
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
                    logger.info(f"📊 Found {len(tokens)} trending tokens. Analyzing...")
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
