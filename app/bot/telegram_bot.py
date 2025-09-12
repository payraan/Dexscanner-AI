from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InputFile, ReplyKeyboardMarkup, KeyboardButton, InputMediaPhoto
from aiogram.filters import Command
from aiogram.utils.media_group import MediaGroupBuilder
from app.core.config import settings
from app.services.ai_analyzer import ai_analyzer
from app.services.redis_client import redis_client
import time
from app.bot.middlewares import SubscriptionMiddleware
import asyncio
import logging
import io

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_main_keyboard():
    """ایجاد کیبورد اصلی ربات"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📈 نتایج سیگنال‌ها")],
            [KeyboardButton(text="💡 راهنما"), KeyboardButton(text="📞 پشتیبانی")]
        ],
        resize_keyboard=True
    )

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
        self.dp.message.register(self.support_handler, Command("support"))
        self.dp.message.register(self.results_handler, Command("results"))

        # اتصال دکمه‌های کیبورد به handler ها
        self.dp.message.register(self.results_handler, F.text == "📈 نتایج سیگنال‌ها")
        self.dp.message.register(self.help_handler, F.text == "💡 راهنما")
        self.dp.message.register(self.support_handler, F.text == "📞 پشتیبانی")
        # Handler جدید برای دکمه AI
        self.dp.callback_query.register(self.ai_analysis_handler, F.data.startswith("ai_analyze_"))
        self.dp.message.register(self.activate_subscription_handler, Command("activatesub"))
        self.dp.message.register(self.broadcast_handler, Command("broadcast"))

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
       user_name = message.from_user.first_name or "کاربر"
       
       # Register user in database
       from app.database.session import get_db
       from app.database.models import User
       from sqlalchemy import select
       from datetime import datetime, timezone
       
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
           
       welcome_message = f"""🎉 {user_name} عزیز، به DexScanner Bot خوش آمدید!

🤖 DexScanner AI ربات یک ابزار قدرتمند برای تحلیل و سیگنال حرفه‌ای توکن‌ها در فضای دکس با قابلیت‌های بی‌نظیر:

📡 اسکن لحظه‌ای: شناسایی سریع و هوشمند توکن‌های محبوب و جدید در صرافی‌های غیرمتمرکز

📊 تحلیل تکنیکال: استفاده از استراتژی‌های معاملاتی پیشرفته مانند شکست مومنتوم و جهش حجم

🧠 تحلیل با هوش مصنوعی: بررسی تخصصی نمودارها با هوش مصنوعی نارموون و ارائه سناریوهای دقیق معاملاتی

📈 نمودارهای حرفه‌ای: چارت‌های کندل استیک با سطوح فیبوناچی و نواحی حمایت/مقاومت

⚡️ سیگنال‌های بلادرنگ: دریافت فوری سیگنال‌های خرید با نقاط ورود و خروج مشخص

🔔 برای فعال‌سازی اشتراک خود، به پشتیبان پیام دهید:
👈 @Narmoonsupport

💡 از دستور /help برای مشاهده راهنما استفاده کنید."""

       await message.answer(welcome_message, reply_markup=get_main_keyboard())

    async def help_handler(self, message: Message):
        """Handle /help command"""
        await message.answer(
            "📋 Available Commands:\n"
            "/start - Start the bot\n"
            "/help - Show this help message"
        )

    async def _is_ai_rate_limited(self, user_id: int) -> bool:
        """Check if user exceeded AI analysis rate limit (10/hour)"""
        if not redis_client.connected:
            return False
        
        RATE_LIMIT_COUNT = 10
        RATE_LIMIT_WINDOW = 3600
        
        key = f"rate_limit:ai:{user_id}"
        current_time = time.time()
        
        try:
            await redis_client.redis_client.zremrangebyscore(key, 0, current_time - RATE_LIMIT_WINDOW)
            request_count = await redis_client.redis_client.zcard(key)
            
            if request_count >= RATE_LIMIT_COUNT:
                return True
                
            await redis_client.redis_client.zadd(key, {str(current_time): current_time})
            await redis_client.redis_client.expire(key, RATE_LIMIT_WINDOW)
            return False
        except Exception as e:
            logger.error(f"Redis rate limit check failed: {e}")
            return False

    async def ai_analysis_handler(self, callback: CallbackQuery):
        """Handle AI analysis button click"""
        user_id = callback.from_user.id
        
        # Rate limiting check
        if await self._is_ai_rate_limited(user_id):
            await callback.answer(
                "⚠️ شما به حداکثر تعداد تحلیل در ساعت رسیده‌اید. لطفاً بعداً تلاش کنید.",
                show_alert=True
            )
            return
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
                )
            else:
                await callback.message.reply("❌ چارت برای تحلیل یافت نشد.")
            
        except Exception as e:
            logger.error(f"AI analysis error: {e}")
            await callback.message.reply("❌ خطا در تحلیل هوش مصنوعی.")

    async def support_handler(self, message: Message):
        """Handle /support command"""
        support_text = "📞 برای ارتباط با پشتیبانی می‌توانید به آیدی زیر پیام دهید:\n\n@Narmoonsupport"
        await message.answer(support_text)

    async def results_handler(self, message: Message):
        """Handle /results command and button click"""
        await message.answer("⏳ در حال دریافت آخرین نتایج موفق ربات...")
    
        from app.database.session import get_db
        from app.database.models import SignalResult
        from sqlalchemy import select
    
        async for session in get_db():
            results = await session.execute(
                select(SignalResult)
                .where(SignalResult.tracking_status == 'SUCCESS', SignalResult.is_rugged == False)
                .order_by(SignalResult.closed_at.desc())
                .limit(30)
            )
            signal_results = results.scalars().all()
    
        if not signal_results:
            await message.answer("😔 متاسفانه نتیجه موفقی برای نمایش در 7 روز گذشته یافت نشد.")
            return

        for result in signal_results:
            try:
                # فقط در صورتی که دیکشنری file_ids وجود دارد و کلید social_wide در آن است
                if result.composite_file_ids and 'social_wide' in result.composite_file_ids:
                    file_id_to_send = result.composite_file_ids['social_wide']
                    caption = (
                        f"📊 **توکن:** `${result.token_symbol}`\n"
                        f"🚀 **رشد:** `+{result.peak_profit_percentage:.2f}%`\n"
                        f"⏱️ **ثبت شده در:** `{result.closed_at.strftime('%Y-%m-%d')}`"
                    )
                    await message.answer_photo(
                        photo=file_id_to_send, # <-- استفاده از file_id مشخص شده
                        caption=caption,
                        parse_mode='Markdown'
                    )

            except Exception as e:
                logger.error(f"Error sending result for {result.id}: {e}")

    async def broadcast_handler(self, message: Message):
        """Handler for broadcast command - test version"""
        # Check admin permission
        if message.from_user.id not in settings.admin_list:
            await message.answer("⛔️ شما اجازه استفاده از این دستور را ندارید.")
            return
        
        # Extract content
        photo_file_id = None
        caption = None
        text_message = None
        
        # Check if replying to a photo
        if message.reply_to_message and message.reply_to_message.photo:
            photo_file_id = message.reply_to_message.photo[-1].file_id
            caption = message.text.replace("/broadcast", "").strip()
            if not caption and message.reply_to_message.caption:
                caption = message.reply_to_message.caption
        else:
            text_message = message.text.replace("/broadcast", "").strip()
            if not text_message:
                await message.answer(
                    "⚠️ استفاده:\n"
                    "🔹 متن: /broadcast متن شما\n"
                    "🔹 عکس: روی عکس ریپلای و /broadcast کپشن"
                )
                return
        
        await message.answer("⏳ در حال دریافت لیست کاربران...")

        # Get all users from database
        from app.database.session import get_db
        from app.database.models import User
        from sqlalchemy import select
        
        all_user_ids = []
        async for session in get_db():
            result = await session.execute(select(User.id))
            all_user_ids = result.scalars().all()
        
        if not all_user_ids:
            await message.answer("❌ هیچ کاربری یافت نشد.")
            return
        
        # Start sending
        await message.answer(f"✅ شروع ارسال به {len(all_user_ids)} کاربر...")
        success_count = 0
        fail_count = 0
        
        for user_id in all_user_ids:
            try:
                if photo_file_id:
                    await self.bot.send_photo(chat_id=user_id, photo=photo_file_id, caption=caption)
                else:
                    await self.bot.send_message(chat_id=user_id, text=text_message)
                success_count += 1
            except Exception as e:
                logger.error(f"Failed to send to {user_id}: {e}")
                fail_count += 1
            
            await asyncio.sleep(0.1)  # Small delay to prevent spam
        
        # Final report
        await message.answer(
            f"🚀 ارسال همگانی کامل شد!\n\n"
            f"✅ موفق: {success_count}\n"
            f"❌ ناموفق: {fail_count}"
        )

    async def start_polling(self):
        """Start bot polling"""
        logger.info("🤖 Starting Telegram bot...")
        await self.dp.start_polling(self.bot)

telegram_bot = TelegramBot()
