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

   def _build_analytical_caption(self, signal: Dict, token: Token) -> str:
       """
       Build caption for analytical updates (not signals anymore)
       """
       token_symbol = signal.get('token', 'N/A')
       price_str = f"${signal.get('price', 0):.8f}"
       
       # Calculate price change if we have previous price
       price_change_str = ""
       if token.last_scan_price and token.last_scan_price > 0:
           change = ((signal.get('price', 0) - token.last_scan_price) / token.last_scan_price) * 100
    
           if abs(change) < 0.01:
               # اگر تغییر ناچیز است، چیزی نمایش نده
               price_change_str = " (بدون تغییر)"
           else:
               emoji = "🟢" if change > 0 else "🔴"
               # استفاده از مقدار مطلق (abs) و حذف علامت + از فرمت
               price_change_str = f" ({emoji} {abs(change):.2f}%)"
       
       # Determine update type
       if not token.last_scan_price:
           update_type = "🆕 اسکن جدید"
       elif token.state == 'TRENDING':
           update_type = "📈 آپدیت روند"
       else:
           update_type = "🔄 آپدیت وضعیت"
       
       # Build support/resistance info
       zones_info = ""
       if signal.get('zones'):
           for zone in signal.get('zones', [])[:3]:  # Top 3 zones
               zone_type = "مقاومت" if 'resistance' in zone['type'] else "حمایت"
               zones_info += f"• {zone_type}: ${zone['price']:.8f}\n"
       
       # Build fibonacci info
       fib_info = ""
       if signal.get('fibonacci_state'):
           fib = signal['fibonacci_state']
           if fib.get('target1'):
               fib_info = f"🎯 تارگت‌ها: ${fib['target1']:.8f} | ${fib.get('target2', 0):.8f}"
       
       caption = (
           f"{update_type} - **${token_symbol}**\n\n"
           f"💰 **قیمت:** `{price_str}`{price_change_str}\n"
           f"📊 **حجم 24h:** `${signal.get('volume_24h', 0):,.0f}`\n"
           f"⏱ **تایم‌فریم:** `{signal.get('timeframe', 'N/A')}`\n\n"
       )
       
       if zones_info:
           caption += f"📍 **سطوح کلیدی:**\n{zones_info}\n"
       
       if fib_info:
           caption += f"{fib_info}\n\n"
       
       caption += f"📜 **آدرس:** `{signal.get('address', 'N/A')}`"
       
       return caption

   async def send_signal(self, signal: Dict, df: pd.DataFrame, token: Token):
       """Send analytical update (renamed from signal for compatibility)"""
       try:
           async for session in get_db():
               result = await session.execute(select(User).where(User.is_subscribed == True))
               subscribed_users = result.scalars().all()
           
           if not subscribed_users:
               logger.warning("No subscribed users found")
               return

           # Build caption using new analytical format
           caption = self._build_analytical_caption(signal, token)
           
           # Add onchain analysis button
           keyboard = [[
               InlineKeyboardButton(text="📊 تحلیل آنچین", callback_data=f"onchain_{signal.get('address')}"),
               InlineKeyboardButton(text="🧠 تحلیل AI", callback_data=f"ai_analyze_{signal.get('address')}")
           ]]
           reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

           # Generate chart
           chart_bytes = chart_generator.create_signal_chart(df, signal)
           
           # Determine if we should reply to existing message
           reply_to_message_id = None
           if token.message_id and token.reply_count < 10:
               reply_to_message_id = token.message_id
               
           sent_count = 0
           first_message_id = None
           before_file_id = None
           
           for user in subscribed_users:
               try:
                   if chart_bytes:
                       photo = BufferedInputFile(chart_bytes, filename=f"{signal.get('token', 'chart')}.png")
                       
                       # Send with or without reply
                       if reply_to_message_id:
                           try:
                               sent_message = await self.bot.send_photo(
                                   chat_id=user.id,
                                   photo=photo,
                                   caption=f"↳ {caption}",  # Add arrow for replies
                                   parse_mode='Markdown',
                                   reply_to_message_id=reply_to_message_id,
                                   reply_markup=reply_markup
                               )
                           except Exception as e:
                               # If reply fails, send as new message
                               logger.warning(f"Reply failed for user {user.id}, sending as new message")
                               sent_message = await self.bot.send_photo(
                                   chat_id=user.id,
                                   photo=photo,
                                   caption=caption,
                                   parse_mode='Markdown',
                                   reply_markup=reply_markup
                               )
                               reply_to_message_id = None  # Reset for next users
                       else:
                           sent_message = await self.bot.send_photo(
                               chat_id=user.id,
                               photo=photo,
                               caption=caption,
                               parse_mode='Markdown',
                               reply_markup=reply_markup
                           )
                       
                       # Store first message info
                       if sent_count == 0:
                           first_message_id = sent_message.message_id
                           if sent_message.photo:
                               before_file_id = sent_message.photo[-1].file_id
                   else:
                       # Fallback to text message if chart fails
                       sent_message = await self.bot.send_message(
                           chat_id=user.id,
                           text=caption,
                           parse_mode='Markdown',
                           reply_markup=reply_markup,
                           reply_to_message_id=reply_to_message_id if reply_to_message_id else None
                       )
                       if sent_count == 0:
                           first_message_id = sent_message.message_id
                   
                   sent_count += 1
               except Exception as e:
                   logger.error(f"Failed to send message to user {user.id}: {e}")

           # Update token's message tracking
           if first_message_id:
               async for session in get_db():
                   # Update token with message info
                   if reply_to_message_id:
                       # It was a reply, increment counter
                       token.reply_count += 1
                   else:
                       # New message thread started
                       token.message_id = first_message_id
                       token.reply_count = 1
                   
                   # Check if token already has active tracking
                   from app.database.models import SignalResult
                   from sqlalchemy import select
                   
                   existing_tracker_result = await session.execute(
                       select(SignalResult).where(
                           SignalResult.token_address == signal.get('address'),
                           SignalResult.tracking_status == 'TRACKING'
                       )
                   )
                   existing_tracker = existing_tracker_result.scalar_one_or_none()
                   
                   # Create tracker if none exists and chart is available
                   if not existing_tracker and before_file_id:
                       new_tracker = SignalResult(
                           alert_id=None,
                           token_address=signal.get('address'),
                           token_symbol=signal.get('token'),
                           signal_price=signal.get('price', 0),
                           before_chart_file_id=before_file_id,
                           tracking_status='TRACKING'
                       )
                       session.add(new_tracker)
                       logger.info(f"✅ Tracking started for {signal.get('token')}. This is the 'Before' state.")
                   
                   await session.commit()
                   break

           logger.info(f"Update sent to {sent_count} users. {'(Reply)' if reply_to_message_id else '(New thread)'}")

       except Exception as e:
           logger.error(f"Critical error in send_signal: {e}", exc_info=True)

telegram_sender = TelegramSender()
