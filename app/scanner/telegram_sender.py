from aiogram import Bot
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from app.core.config import settings
from app.scanner.chart_generator import chart_generator
from app.database.session import get_db
from app.database.models import User, Alert, Token
from sqlalchemy import select
from typing import Dict
import logging
import pandas as pd
from datetime import datetime

logger = logging.getLogger(__name__)

class TelegramSender:
    def __init__(self):
        self.bot = Bot(token=settings.BOT_TOKEN)

    async def send_signal(self, signal: Dict, df: pd.DataFrame):
        """Send trading signal to all subscribed users with reply chain"""
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

            # Find token in database to get last message_id for reply chain
            reply_to_message_id = None
            token_id = None
            
            async for session in get_db():
                # Find token
                token_result = await session.execute(
                    select(Token).where(Token.address == signal['address'])
                )
                token_record = token_result.scalar_one_or_none()
                
                if token_record:
                    token_id = token_record.id
                    # Get last alert for this token
                    last_alert_result = await session.execute(
                        select(Alert).where(Alert.token_id == token_record.id)
                        .order_by(Alert.timestamp.desc()).limit(1)
                    )
                    last_alert = last_alert_result.scalar_one_or_none()
                    if last_alert and last_alert.message_id:
                        reply_to_message_id = last_alert.message_id
                        logger.info("Reply chain established", 
                                  extra={'token_symbol': signal['token'], 'reply_to_message_id': reply_to_message_id})
                break

            # Prepare message with timeframe info
            signal_emojis = {
                'high_volume': '💰',
                'momentum_surge': '🚀',
                'volume_spike': '📊',
                'momentum_breakout': '📈',
                'support_bounce': '🔄',
                'volume_surge': '📊'
            }
            emoji = signal_emojis.get(signal['signal_type'], '🔔')

            timeframe_info = f"\nتایم‌فریم: `{signal.get('timeframe', 'hour/1')}`" if signal.get('timeframe') else ""

            caption = (
                f"{emoji} سیگنال شناسایی شد {emoji}\n\n"
                f"توکن: `{signal['token']}`\n"
                f"نوع: `{signal['signal_type'].replace('_', ' ').title()}`\n"
                f"قدرت: `{signal.get('strength', 0):.1f}/10`\n"
                f"قیمت: `${signal['price']:.8f}`\n"
                f"حجم 24 ساعته: `${signal['volume_24h']:,.0f}`{timeframe_info}\n\n"
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
            sent_message_id = None
            
            for user in subscribed_users:
                try:
                    if chart_bytes:
                        photo = BufferedInputFile(chart_bytes, filename=f"{signal['token']}_chart.png")
                        sent_message = await self.bot.send_photo(
                            chat_id=user.id,
                            photo=photo,
                            caption=caption,
                            parse_mode='Markdown',
                            reply_markup=reply_markup,
                            reply_to_message_id=reply_to_message_id
                        )
                    else:
                        sent_message = await self.bot.send_message(
                            chat_id=user.id,
                            text=caption,
                            parse_mode='Markdown',
                            reply_markup=reply_markup,
                            reply_to_message_id=reply_to_message_id
                        )
                    
                    # Store message_id for reply chain (only from first user for simplicity)
                    if sent_count == 0:
                        sent_message_id = sent_message.message_id
                    
                    sent_count += 1
                    
                except Exception as e:
                    logger.error("Failed to send message to user", 
                               extra={'user_id': user.id, 'error': str(e)})

            # Save alert with message_id for reply chain
            if token_id and sent_message_id:
                async for session in get_db():
                    new_alert = Alert(
                        token_id=token_id,
                        strategy=signal['signal_type'],
                        price_at_alert=signal['price'],
                        message_id=sent_message_id,
                        chat_id=subscribed_users[0].id if subscribed_users else None,
                        timestamp=datetime.utcnow()
                    )
                    session.add(new_alert)
                    await session.commit()
                    break

            logger.info("Signal sent successfully", 
                       extra={'token_symbol': signal['token'], 'user_count': sent_count, 'total_users': len(subscribed_users)})

        except Exception as e:
            logger.error("Failed to send signal", 
                        extra={'token_symbol': signal.get('token', 'unknown'), 'error': str(e)})

telegram_sender = TelegramSender()
