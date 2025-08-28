from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from app.database.session import SessionLocal
from app.database.models import User
from sqlalchemy import select

class SubscriptionMiddleware(BaseMiddleware):
   async def __call__(
       self,
       handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
       event: Message | CallbackQuery,
       data: Dict[str, Any]
   ) -> Any:
       # Skip middleware for admin commands and /start
       if isinstance(event, Message) and event.text:
           public_commands = ['/start', '/help', '/support', '/results', '📈 نتایج سیگنال‌ها', '💡 راهنما', '📞 پشتیبانی']
           if any(event.text.startswith(cmd) for cmd in public_commands):
               return await handler(event, data) 
      
       user_id = event.from_user.id

       # Check subscription in database
       async with SessionLocal() as session:
           result = await session.execute(
               select(User).where(User.id == user_id)
           )
           user = result.scalar_one_or_none()

           if not user or not user.is_subscribed:
               message_text = "⚠️ شما اشتراک فعال ندارید. لطفا برای فعال‌سازی با ادمین تماس بگیرید."
               if isinstance(event, Message):
                   await event.answer(message_text)
               elif isinstance(event, CallbackQuery):
                   await event.answer(message_text, show_alert=True)
               return

       return await handler(event, data)
