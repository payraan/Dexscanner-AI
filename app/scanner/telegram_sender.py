from aiogram import Bot
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from app.core.config import settings
from app.scanner.chart_generator import chart_generator
from typing import Dict
import logging
import pandas as pd

logger = logging.getLogger(__name__)

class TelegramSender:
    def __init__(self):
        self.bot = Bot(token=settings.BOT_TOKEN)

    async def send_signal(self, signal: Dict, df: pd.DataFrame):
        """Send trading signal with chart to Telegram channel"""
        try:
            signal_emojis = {
                'high_volume': '💰',
                'momentum_surge': '🚀',
                'volume_spike': '📊',
                'momentum_breakout': '📈',
                'support_bounce': '🔄'
            }
            emoji = signal_emojis.get(signal['signal_type'], '🔔')

            # Create caption with Markdown formatting
            caption = (
                f"{emoji} **SIGNAL DETECTED** {emoji}\n\n"
                f"**Token:** `{signal['token']}`\n"
                f"**Type:** `{signal['signal_type'].replace('_', ' ').title()}`\n"
                f"**Strength:** `{signal.get('strength', 0):.1f}/10`\n"
                f"**Price:** `${signal['price']:.8f}`\n"
                f"**24h Volume:** `${signal['volume_24h']:,.0f}`\n\n"
                f"**Contract:** `{signal['address']}`"
            )

            # Add multiple signals info if available
            if 'all_signals' in signal and len(signal['all_signals']) > 1:
                all_signals = ', '.join(signal['all_signals'])
                caption += f"\n\n**Multiple Signals:** `{all_signals}`"

            # Create AI analysis button
            keyboard = [
                [InlineKeyboardButton(
                    text="🧠 تحلیل با هوش مصنوعی",
                    callback_data=f"ai_analyze_{signal['address']}"
                )]
            ]
            reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

            # Generate chart directly with received DataFrame
            chart_bytes = chart_generator.create_signal_chart(df, signal, signal)

            if chart_bytes:
                photo = BufferedInputFile(chart_bytes, filename=f"{signal['token']}_chart.png")
                await self.bot.send_photo(
                    chat_id=settings.CHAT_ID,
                    photo=photo,
                    caption=caption,
                    parse_mode='Markdown',
                    reply_markup=reply_markup
                )
            else:
                # Fallback to text message with button
                await self.bot.send_message(
                    chat_id=settings.CHAT_ID,
                    text=caption,
                    parse_mode='Markdown',
                    reply_markup=reply_markup
                )

            logger.info(f"📤 Signal sent for {signal['token']}")

        except Exception as e:
            logger.error(f"❌ Failed to send signal for {signal['token']}: {e}")

telegram_sender = TelegramSender()
