from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InputFile
from aiogram.filters import Command
from app.core.config import settings
from app.services.ai_analyzer import ai_analyzer
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

    def setup_handlers(self):
        """Setup message and callback handlers"""
        self.dp.message.register(self.start_handler, Command("start"))
        self.dp.message.register(self.help_handler, Command("help"))
        # Handler جدید برای دکمه AI
        self.dp.callback_query.register(self.ai_analysis_handler, F.data.startswith("ai_analyze_"))

    async def start_handler(self, message: Message):
        """Handle /start command"""
        await message.answer(
            "🚀 DexScanner Bot Started!\n\n"
            "This bot will scan Solana tokens and send alerts."
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
