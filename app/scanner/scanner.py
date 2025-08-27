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
                logger.warning("Skipping token due to health issues", 
                             extra={'token_symbol': token['symbol'], 'health_status': health_status})
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
                    logger.info("Signal queued for processing", 
                              extra={'token_symbol': signal['token'], 'signal_type': signal['signal_type']})
                else:
                    logger.info("Signal skipped due to cooldown", 
                              extra={'token_symbol': signal['token']})

            await asyncio.sleep(2) 

        logger.info("Health screening completed", 
                   extra={'healthy_tokens': healthy_tokens, 'total_tokens': len(tokens)})

        if not signals_to_send:
            logger.info("No new signals to send")
            return

        logger.info("Preparing to send signals", 
                   extra={'signal_count': len(signals_to_send)})
        
        # Send all valid signals
        for signal, df in signals_to_send:
            await telegram_sender.send_signal(signal, df)
            await cooldown_service.record_signal(signal)

    async def start_scanning(self):
        """Start background scanning loop"""
        self.running = True
        logger.info("Scanner started", extra={'scan_interval': settings.SCAN_INTERVAL})

        while self.running:
            try:
                self.scan_count += 1
                logger.info("Starting scan cycle", extra={'scan_number': self.scan_count})
                
                tokens = await data_provider.fetch_trending_tokens(
                    limit=settings.TRENDING_TOKENS_LIMIT
                )

                if tokens:
                    # Store tokens in database with health status
                    await token_service.store_tokens_with_health(tokens)
                    logger.info("Tokens fetched and stored", 
                              extra={'token_count': len(tokens)})
                    await self._analyze_and_send_signals(tokens)
                else:
                    logger.warning("No trending tokens found in this scan cycle")
                
                logger.info("Scan cycle completed", extra={'scan_number': self.scan_count})
                await asyncio.sleep(settings.SCAN_INTERVAL)

            except Exception as e:
                logger.error("Error in scanner loop", 
                           extra={'error': str(e), 'scan_number': self.scan_count}, exc_info=True)
                await asyncio.sleep(60)

    def stop(self):
        """Stop scanning"""
        self.running = False
        logger.info("Scanner stopped")

token_scanner = TokenScanner()
