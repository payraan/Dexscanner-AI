import asyncio
import logging
from typing import List, Dict

# --- Import the new service ---
from app.services.cooldown_service import token_state_service
# --- Keep other imports ---
from app.scanner.data_provider import data_provider
from app.scanner.analysis import analysis_engine
from app.core.config import settings
from app.scanner.telegram_sender import telegram_sender
from app.services.token_service import token_service
from app.scanner.token_health import token_health_checker
from app.services.bitquery_service import bitquery_service

logger = logging.getLogger(__name__)

class TokenScanner:
    def __init__(self):
        self.running = False
        self.scan_count = 0

    async def _analyze_and_send_signals(self, tokens: List[Dict]):
        """Analyze tokens and send signals based on their state."""
        
        signals_to_send = []
        healthy_tokens = 0
        
        for token_data in tokens:
            # First check token health
            df_for_health = await data_provider.fetch_ohlcv(
                token_data['pool_id'], timeframe="hour", aggregate="1", limit=50
            )
            health_status = await token_health_checker.check_token_health(df_for_health, token_data)
            
            if health_status in ['rugged', 'suspicious']:
                logger.warning(f"Skipping token due to health issues: {token_data['symbol']} ({health_status})")
                continue
            
            healthy_tokens += 1
            
            # --- NEW: Check if a signal can be sent for this token BEFORE deep analysis ---
            can_send = await token_state_service.can_send_signal(token_data['address'])
            if not can_send:
                logger.info(f"Token {token_data['symbol']} is in COOLDOWN/SIGNALED state, skipping deep analysis.")
                continue # Skip to the next token
            # --- END NEW ---

            # On-chain analysis filter
            if healthy_tokens <= 10: # Increased limit for more on-chain checks
                try:
                    holder_stats = await bitquery_service.get_holder_stats(token_data['address'])
                    if holder_stats:
                        if holder_stats['top_10_concentration'] > 60:
                            logger.warning(f"Skipping {token_data['symbol']} - High concentration: {holder_stats['top_10_concentration']}%")
                            continue
                        token_data['holder_stats'] = holder_stats
                        
                        if holder_stats['top_10_concentration'] < 30:
                            liquidity_stats = await bitquery_service.get_liquidity_stats(token_data['address'])
                            if liquidity_stats:
                                token_data['liquidity_stats'] = liquidity_stats
                except Exception as e:
                    logger.error(f"Bitquery analysis failed for {token_data['symbol']}: {e}")
            
            signal, df = await analysis_engine.analyze_token(token_data)
            
            if signal and df is not None and not df.empty:
                # The check is already done, so we just queue the signal
                signal['health_status'] = health_status
                signals_to_send.append((signal, df))
                logger.info(f"Signal QUEUED for {signal['token']} ({signal['signal_type']})")

            await asyncio.sleep(1) 

        logger.info(f"Health screening completed. Healthy tokens: {healthy_tokens}/{len(tokens)}")

        if not signals_to_send:
            logger.info("No new signals to send in this cycle.")
            return

        logger.info(f"Preparing to send {len(signals_to_send)} new signals.")
        
        for signal, df in signals_to_send:
            await telegram_sender.send_signal(signal, df)
            # --- NEW: Use the new service to record the signal ---
            await token_state_service.record_signal_sent(
                signal['address'],
                signal.get('price', 0)
            )
            # --- END NEW ---

    async def start_scanning(self):
        """Start background scanning loop"""
        self.running = True
        logger.info(f"Scanner started. Scan interval: {settings.SCAN_INTERVAL} seconds")

        while self.running:
            try:
                self.scan_count += 1
                logger.info(f"--- Starting Scan Cycle #{self.scan_count} ---")
                
                tokens = await data_provider.fetch_trending_tokens(
                    limit=settings.TRENDING_TOKENS_LIMIT
                )

                if tokens:
                    await token_service.store_tokens_with_health(tokens)
                    logger.info(f"Fetched and stored {len(tokens)} tokens.")
                    await self._analyze_and_send_signals(tokens)
                else:
                    logger.warning("No trending tokens found in this scan cycle.")
                
                logger.info(f"--- Scan Cycle #{self.scan_count} Completed ---")
                await asyncio.sleep(settings.SCAN_INTERVAL)

            except Exception as e:
                logger.error(f"CRITICAL ERROR in scanner loop #{self.scan_count}: {e}", exc_info=True)
                await asyncio.sleep(60)

    def stop(self):
        """Stop scanning"""
        self.running = False
        logger.info("Scanner stopped")

token_scanner = TokenScanner()
