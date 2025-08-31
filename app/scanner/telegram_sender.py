from aiogram import Bot
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from app.core.config import settings
from app.scanner.chart_generator import chart_generator
from app.database.session import get_db
from app.database.models import User, Alert, Token, SignalResult
from sqlalchemy import select
from typing import Dict
import logging
import pandas as pd
from datetime import datetime

logger = logging.getLogger(__name__)

class TelegramSender:
    def __init__(self):
        self.bot = Bot(token=settings.BOT_TOKEN)

    def _build_signal_caption(self, signal: Dict) -> str:
        """
        Creatively builds the signal message using a storytelling format and confidence levels.
        """
        gem_score = signal.get('gem_score', 0)
        token_symbol = signal.get('token', 'N/A')
        signal_type = signal.get('signal_type', 'unknown').replace('_', ' ').title()
        
        # 1. Determine Confidence Level and Header
        if gem_score >= 85:
            confidence_level = "اعتماد بالا 🔥"
            header = f"🔥 **شکار الماس: ${token_symbol}** 🔥"
        elif gem_score >= 65:
            confidence_level = "اعتماد متوسط ⚡️"
            header = f"⚡️ **فرصت طلایی: ${token_symbol}** ⚡️"
        else:
            confidence_level = "لیست زیر نظر 💡"
            header = f"💡 **تحت نظر: ${token_symbol}** 💡"
            
        # 2. Build the Story Chapters
        # Chapter 1: The Discovery
        story_discovery = "ربات ما افزایش فعالیت بازار در این توکن را شناسایی کرده و آن را تحت نظر گرفت."
        if 'volume_explosion' in signal.get('all_signals', []):
            story_discovery = f"با شناسایی **جهش حجم ناگهانی**، {token_symbol} وارد رادار شکارچی ما شد."

        # Chapter 2: The Trigger (Main Event)
        story_trigger = f"اکنون، یک رویداد **{signal_type}** به عنوان ماشه شلیک عمل کرده است."
        if 'breakout' in signal.get('signal_type', ''):
            level = signal.get('level', 0)
            zone_type = "ناحیه طلایی" if "golden" in signal.get('zones', [{}])[0].get('type', '') else "ناحیه مقاومتی کلیدی"
            story_trigger = f"قیمت با قدرت **{zone_type}** را در حدود `${level:.8f}` شکسته و بالای آن تثبیت شده است."

        # Chapter 3: Key Details
        price_str = f"${signal.get('price', 0):.8f}"
        volume_str = f"${signal.get('volume_24h', 0):,.0f}"
        
        # 3. Assemble the final caption
        caption = (
            f"{header}\n\n"
            f"**سطح اعتماد:** `{confidence_level}`\n"
            f"**امتیاز نهایی:** `{gem_score:.1f}/100`\n\n"
            f"**📖 داستان سیگنال:**\n"
            f"📍 **فصل اول (کشف):** {story_discovery}\n"
            f"📍 **فصل دوم (ماشه شلیک):** {story_trigger}\n\n"
            f"**📊 جزئیات کلیدی:**\n"
            f"- **قیمت فعلی:** `{price_str}`\n"
            f"- **حجم ۲۴ ساعته:** `{volume_str}`\n"
            f"- **تایم‌فریم تحلیل:** `{signal.get('timeframe', 'N/A')}`\n\n"
            f"**قرارداد:** `{signal.get('address', 'N/A')}`"
        )
        return caption

    async def send_signal(self, signal: Dict, df: pd.DataFrame):
        """Send trading signal using the new creative format."""
        try:
            async for session in get_db():
                result = await session.execute(select(User).where(User.is_subscribed == True))
                subscribed_users = result.scalars().all()
            
            if not subscribed_users:
                logger.warning("No subscribed users found")
                return

            reply_to_message_id, token_id = None, None
            async for session in get_db():
                token_address = signal.get('address')
                if not token_address:
                    logger.error("Signal dictionary is missing 'address' key.")
                    return
                token_result = await session.execute(select(Token).where(Token.address == token_address))
                token_record = token_result.scalar_one_or_none()
                if token_record:
                    token_id = token_record.id
                    # Reply chain logic can be added here if needed in the future
                break

            # --- NEW: Build the creative caption ---
            caption = self._build_signal_caption(signal)

            keyboard = [[InlineKeyboardButton(text="🧠 تحلیل هوش مصنوعی", callback_data=f"ai_analyze_{signal.get('address')}")]]
            reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

            chart_bytes = chart_generator.create_signal_chart(df, signal)

            sent_count, before_file_id = 0, None
            for user in subscribed_users:
                try:
                    if chart_bytes:
                        photo = BufferedInputFile(chart_bytes, filename=f"{signal.get('token', 'chart')}.png")
                        sent_message = await self.bot.send_photo(
                            chat_id=user.id,
                            photo=photo,
                            caption=caption,
                            parse_mode='Markdown',
                            reply_markup=reply_markup
                        )
                        if sent_count == 0 and sent_message.photo:
                            before_file_id = sent_message.photo[-1].file_id
                    else: # Fallback to text message if chart fails
                        sent_message = await self.bot.send_message(
                            chat_id=user.id,
                            text=caption,
                            parse_mode='Markdown',
                            reply_markup=reply_markup
                        )
                    
                    if sent_count == 0:
                        sent_message_id = sent_message.message_id
                    sent_count += 1
                except Exception as e:
                    logger.error(f"Failed to send message to user {user.id}: {e}")

            # Save alert and tracker record
            if token_id and before_file_id:
                async for session in get_db():
                    new_alert = Alert(
                        token_id=token_id,
                        strategy=signal.get('signal_type'),
                        price_at_alert=signal.get('price', 0),
                        message_id=sent_message_id,
                        chat_id=subscribed_users[0].id,
                        timestamp=datetime.utcnow()
                    )
                    session.add(new_alert)
                    await session.flush()

                    # --- BUG FIX: Use 'tracking_status' instead of 'status' ---
                    new_tracker = SignalResult(
                        alert_id=new_alert.id,
                        token_address=signal.get('address'),
                        token_symbol=signal.get('token'),
                        signal_price=signal.get('price', 0),
                        before_chart_file_id=before_file_id,
                        tracking_status='TRACKING' # Corrected field name
                    )
                    session.add(new_tracker)
                    logger.info(f"Started tracking signal for {signal.get('token')} with file_id {before_file_id}")
                    await session.commit()
                    break

            logger.info(f"Signal send process completed. Sent to {sent_count} users.")

        except Exception as e:
            logger.error(f"A critical error occurred in send_signal: {e}", exc_info=True)

telegram_sender = TelegramSender()
