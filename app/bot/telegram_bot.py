from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InputFile, ReplyKeyboardMarkup, KeyboardButton, InputMediaPhoto
from aiogram.filters import Command
from aiogram.utils.media_group import MediaGroupBuilder
from app.core.config import settings
from app.services.ai_analyzer import ai_analyzer
from app.bot.middlewares import SubscriptionMiddleware
import asyncio
import logging
import io
from app.services.bitquery_service import bitquery_service

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
        self.dp.callback_query.register(self.onchain_analysis_handler, F.data.startswith("onchain_"))
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
                   created_at=datetime.now(timezone.utc)
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
                )
            else:
                await callback.message.reply("❌ چارت برای تحلیل یافت نشد.")
            
        except Exception as e:
            logger.error(f"AI analysis error: {e}")
            await callback.message.reply("❌ خطا در تحلیل هوش مصنوعی.")

    async def onchain_analysis_handler(self, callback: CallbackQuery):
        """Handle OnChain analysis button click"""
        await callback.answer("📊 در حال دریافت داده‌های آنچین...")
        
        try:
            token_address = callback.data.replace("onchain_", "")
            
            # Import bitquery service
            from app.services.bitquery_service import bitquery_service
            
            holder_stats = await bitquery_service.get_holder_stats(token_address)
            liquidity_stats = await bitquery_service.get_liquidity_stats(token_address)
            total_holders = await bitquery_service.get_total_holders(token_address)

            if not holder_stats and not liquidity_stats:
                await callback.message.reply("❌ داده‌های آنچین در حال حاضر در دسترس نیست.")
                return

            # ساخت متن پاسخ
            text = "📊 **تحلیل آنچین**\n\n"

            if holder_stats:
                concentration = holder_stats.get('top_10_concentration', 'N/A')
                text += f"💎 **توزیع هولدرها:**\n"
                if total_holders is not None:
                    try:
                        total_holders_int = int(total_holders)
                        text += f"• تعداد کل هولدرها: `{total_holders_int:,}`\n"
                    except (ValueError, TypeError):
                        text += f"• تعداد کل هولدرها: `{total_holders}`\n"
                text += f"• تمرکز Top 10: `{concentration}%`\n"
                text += f"• امتیاز توزیع: `{holder_stats.get('distribution_score', 0):.1f}/100`\n\n"

            # --- بخش اضافه‌شده برای نمایش جریان نقدینگی ---
            if liquidity_stats:
                net_flow = liquidity_stats.get('net_flow_24h_usd', 0)
                stability_ratio = liquidity_stats.get('liquidity_stability_ratio', 0)
                flow_emoji = "🟢" if net_flow > 0 else "🔴"
                
                text += f"💰 **جریان نقدینگی (24h):**\n"
                text += f"• خالص: {flow_emoji} `${net_flow:,.0f}`\n"
                text += f"• نسبت پایداری: `{stability_ratio:.2f}`\n"
            # --- پایان بخش اضافه‌شده ---

            await callback.message.reply(text, parse_mode='Markdown')            

        except Exception as e:
            logger.error(f"OnChain analysis error: {e}")
            await callback.message.reply("❌ خطا در دریافت داده‌های آنچین")


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
                .limit(5)
            )
            signal_results = results.scalars().all()
    
        if not signal_results:
            await message.answer("😔 متاسفانه نتیجه موفقی برای نمایش در 7 روز گذشته یافت نشد.")
            return

        for result in signal_results:
            try:
                # فقط در صورتی که تصویر نهایی (مونتاژ شده) وجود دارد، آن را نمایش بده
                if result.after_chart_file_id:
                    caption = (
                        f"📊 **توکن:** `${result.token_symbol}`\n"
                        f"🚀 **رشد:** `+{result.peak_profit_percentage:.2f}%`\n"
                        f"⏱️ **ثبت شده در:** `{result.closed_at.strftime('%Y-%m-%d')}`"
                    )
                    await message.answer_photo(
                        photo=result.after_chart_file_id,
                        caption=caption,
                        parse_mode='Markdown'
                    )
            except Exception as e:
                logger.error(f"Error sending result for {result.id}: {e}")

    async def start_polling(self):
        """Start bot polling"""
        logger.info("🤖 Starting Telegram bot...")
        await self.dp.start_polling(self.bot)

telegram_bot = TelegramBot()
