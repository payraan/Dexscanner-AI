from aiogram import Bot
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from app.core.config import settings
from app.scanner.chart_generator import chart_generator
from app.database.session import get_db
from app.database.models import User
from sqlalchemy import select
from typing import Dict
import logging
import pandas as pd

logger = logging.getLogger(__name__)

class TelegramSender:
    def __init__(self):
        self.bot = Bot(token=settings.BOT_TOKEN)

    async def send_signal(self, signal: Dict, df: pd.DataFrame):
        """Send trading signal to all subscribed users"""
        try:
            # Get all subscribed users
            async for session in get_db():
                result = await session.execute(
                    select(User).where(User.is_subscribed == True)
                )
                subscribed_users = result.scalars().all()
            
            if not subscribed_users:
                logger.warning("No subscribed users found")
                return

            # Prepare message
            signal_emojis = {
                'high_volume': '💰',
                'momentum_surge': '🚀',
                'volume_spike': '📊',
                'momentum_breakout': '📈',
                'support_bounce': '🔄'
            }
            emoji = signal_emojis.get(signal['signal_type'], '🔔')

            caption = (
                f"{emoji} سیگنال شناسایی شد {emoji}\n\n"
                f"توکن: `{signal['token']}`\n"
                f"نوع: `{signal['signal_type'].replace('_', ' ').title()}`\n"
                f"قدرت: `{signal.get('strength', 0):.1f}/10`\n"
                f"قیمت: `${signal['price']:.8f}`\n"
                f"حجم 24 ساعته: `${signal['volume_24h']:,.0f}`\n\n"
                f"آدرس قرارداد: `{signal['address']}`"
            )

            keyboard = [
                [InlineKeyboardButton(
                    text="🧠 تحلیل هوش مصنوعی",
                    callback_data=f"ai_analyze_{signal['address']}"
                )]
            ]
            reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

            # Generate chart
            chart_bytes = chart_generator.create_signal_chart(df, signal, signal)

            # Send to all subscribed users
            sent_count = 0
            for user in subscribed_users:
                try:
                    if chart_bytes:
                        photo = BufferedInputFile(chart_bytes, filename=f"{signal['token']}_chart.png")
                        await self.bot.send_photo(
                            chat_id=user.id,
                            photo=photo,
                            caption=caption,
                            parse_mode='Markdown',
                            reply_markup=reply_markup
                        )
                    else:
                        await self.bot.send_message(
                            chat_id=user.id,
                            text=caption,
                            parse_mode='Markdown',
                            reply_markup=reply_markup
                        )
                    sent_count += 1
                    
                except Exception as e:
                    logger.error(f"Failed to send to user {user.id}: {e}")

            logger.info(f"Signal sent to {sent_count}/{len(subscribed_users)} users for {signal['token']}")

        except Exception as e:
            logger.error(f"Failed to send signal for {signal['token']}: {e}")

telegram_sender = TelegramSender()
