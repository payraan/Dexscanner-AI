from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InputFile
from aiogram.filters import Command
from app.core.config import settings
from app.services.ai_analyzer import ai_analyzer
from app.bot.middlewares import SubscriptionMiddleware
import asyncio
import logging
import io

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TelegramBot:
    def __init__(self):
        self.bot = Bot(token=settings.BOT_TOKEN)
        self.dp = Dispatcher()
        self.setup_handlers()
        self.dp.message.middleware(SubscriptionMiddleware())
        self.dp.callback_query.middleware(SubscriptionMiddleware())

    def setup_handlers(self):
        """Setup message and callback handlers"""
        self.dp.message.register(self.start_handler, Command("start"))
        self.dp.message.register(self.help_handler, Command("help"))
        # Handler جدید برای دکمه AI
        self.dp.callback_query.register(self.ai_analysis_handler, F.data.startswith("ai_analyze_"))
        self.dp.message.register(self.activate_subscription_handler, Command("activatesub"))

    async def activate_subscription_handler(self, message: Message):
        """Handle /activatesub command for admins"""
        if message.from_user.id not in settings.admin_list:
            await message.answer("شما اجازه استفاده از این دستور را ندارید.")
            return
    
        try:
            args = message.text.split()[1:]
            user_id = int(args[0])
            days = int(args[1]) if len(args) > 1 else 30
        
            from app.database.session import get_db
            from app.database.models import User
            from sqlalchemy import select
            from datetime import datetime, timedelta
        
            async for session in get_db():
                result = await session.execute(
                    select(User).where(User.id == user_id)
                )
                user = result.scalar_one_or_none()
            
                if user:
                    user.is_subscribed = True
                    user.subscription_end_date = datetime.utcnow() + timedelta(days=days)
                    await session.commit()
                    await message.answer(f"اشتراک کاربر {user_id} برای {days} روز فعال شد.")
                else:
                    await message.answer("کاربر یافت نشد.")
        
        except (IndexError, ValueError):
            await message.answer("استفاده: /activatesub USER_ID [DAYS]")

    async def start_handler(self, message: Message):
        """Handle /start command and register new users"""
        user_id = message.from_user.id
    
        # Register user in database
        from app.database.session import get_db
        from app.database.models import User
        from sqlalchemy import select
        from datetime import datetime
    
        async for session in get_db():
            result = await session.execute(
                select(User).where(User.id == user_id)
            )
            user = result.scalar_one_or_none()
        
            if not user:
                new_user = User(
                    id=user_id,
                    is_subscribed=False,
                    created_at=datetime.utcnow()
                )
                session.add(new_user)
                await session.commit()
    
        await message.answer(
            "🚀 خوش آمدید به DexScanner Bot!\n\n"
            "برای استفاده از ربات، نیاز به اشتراک فعال دارید.\n"
            "برای فعال‌سازی با ادمین تماس بگیرید."
        )

    async def help_handler(self, message: Message):
        """Handle /help command"""
        await message.answer(
            "📋 Available Commands:\n"
            "/start - Start the bot\n"
            "/help - Show this help message"
        )

    async def ai_analysis_handler(self, callback: CallbackQuery):
        """Handle AI analysis button click"""
        await callback.answer("🧠 در حال تحلیل...")
    
        try:
            # Extract token address from callback
            token_address = callback.data.replace("ai_analyze_", "")
        
            # Get chart from original message
            if callback.message.photo:
                # Download chart image
                photo = callback.message.photo[-1]  # Get highest resolution
                file = await self.bot.get_file(photo.file_id)
                file_bytes = await self.bot.download_file(file.file_path)
            
                # Send to AI for analysis
                from app.services.ai_analyzer import ai_analyzer
                analysis = await ai_analyzer.analyze_chart(file_bytes.read())
            
                # Send analysis as reply
                await callback.message.reply(
                    f"🧠 تحلیل هوش مصنوعی:\n\n{analysis}",
                    parse_mode='Markdown'
                )
            else:
                await callback.message.reply("❌ چارت برای تحلیل یافت نشد.")
            
        except Exception as e:
            logger.error(f"AI analysis error: {e}")
            await callback.message.reply("❌ خطا در تحلیل هوش مصنوعی.")

    async def start_polling(self):
        """Start bot polling"""
        logger.info("🤖 Starting Telegram bot...")
        await self.dp.start_polling(self.bot)

telegram_bot = TelegramBot()
