from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from app.database.session import get_db
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
           if event.text.startswith('/activatesub') or event.text.startswith('/start'):
               return await handler(event, data)
       
       user_id = event.from_user.id

       # Check subscription in database
       async for session in get_db():
           result = await session.execute(
               select(User).where(User.id == user_id)
           )
           user = result.scalar_one_or_none()

           if not user or not user.is_subscribed:
               if isinstance(event, Message):
                   await event.answer("⚠️ شما اشتراک فعال ندارید.")
               else:
                   await event.answer("⚠️ شما اشتراک فعال ندارید.", show_alert=True)
               return

       return await handler(event, data)
