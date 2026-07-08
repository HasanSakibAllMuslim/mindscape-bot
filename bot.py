# ============================================
# Telegram Auto-Poster Bot - The Mindscape
# Pella হোস্টিং এর জন্য প্রস্তুত
# ============================================

import asyncio
import logging
import sqlite3
import os
import time
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties
from telethon import TelegramClient
from telethon.errors import FloodWaitError

# ============================================
# 🔑 কনফিগারেশন - এনভায়রনমেন্ট ভেরিয়েবল থেকে নিবে
# ============================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "8845721156:AAHReoBOGgyNnaQ7Akg0Fn0yfGu79x1s6cY")
STORAGE_CHANNEL_ID = int(os.getenv("STORAGE_CHANNEL_ID", "-1004335367175"))
TARGET_CHANNEL = os.getenv("TARGET_CHANNEL", "@the_mindscape")
API_ID = int(os.getenv("API_ID", "36102821"))
API_HASH = os.getenv("API_HASH", "95bcc8a63f351e8873bd4da5858ee8b8")

DEFAULT_INTERVAL = 10
DEFAULT_CAPTION = "🎬 You May Subscribe Our Channel💫"
SQLITE_TIMEOUT = 30
DB_PATH = "bot_data.db"

# ============================================
# ডাটাবেস
# ============================================

def get_db_connection():
    try:
        conn = sqlite3.connect(DB_PATH, timeout=SQLITE_TIMEOUT)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn
    except Exception as e:
        logging.error(f"ডাটাবেস কানেক্ট করতে ব্যর্থ: {e}")
        return None

def init_db():
    conn = get_db_connection()
    if not conn:
        return
    
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS posted_videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER NOT NULL,
            file_id TEXT NOT NULL,
            posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bot_settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        INSERT OR IGNORE INTO bot_settings (key, value) VALUES
        ('post_interval', '10'),
        ('global_caption', '🎬 You May Subscribe Our Channel💫'),
        ('bot_status', 'active'),
        ('last_message_id', '0'),
        ('first_run', 'true')
    """)
    conn.commit()
    conn.close()
    logging.info("✅ ডাটাবেস প্রস্তুত")

def get_setting(key):
    conn = get_db_connection()
    if not conn:
        return None
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT value FROM bot_settings WHERE key = ?", (key,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None
    except Exception as e:
        logging.error(f"get_setting এরর: {e}")
        conn.close()
        return None

def update_setting(key, value):
    for attempt in range(3):
        conn = get_db_connection()
        if not conn:
            continue
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT OR REPLACE INTO bot_settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)", (key, value))
            conn.commit()
            conn.close()
            return True
        except sqlite3.OperationalError as e:
            if "locked" in str(e):
                time.sleep(1)
                continue
        except Exception as e:
            logging.error(f"update_setting এরর: {e}")
            conn.close()
            return False
    return False

def is_video_posted(message_id):
    conn = get_db_connection()
    if not conn:
        return False
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT 1 FROM posted_videos WHERE message_id = ?", (message_id,))
        result = cursor.fetchone()
        conn.close()
        return result is not None
    except Exception as e:
        logging.error(f"is_video_posted এরর: {e}")
        conn.close()
        return False

def mark_video_posted(message_id, file_id):
    for attempt in range(3):
        conn = get_db_connection()
        if not conn:
            continue
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO posted_videos (message_id, file_id) VALUES (?, ?)", (message_id, file_id))
            conn.commit()
            conn.close()
            return True
        except sqlite3.OperationalError as e:
            if "locked" in str(e):
                time.sleep(1)
                continue
        except Exception as e:
            logging.error(f"mark_video_posted এরর: {e}")
            conn.close()
            return False
    return False

def get_stats():
    conn = get_db_connection()
    if not conn:
        return {'posted': 0}
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM posted_videos")
        total = cursor.fetchone()[0]
        conn.close()
        return {'posted': total}
    except Exception as e:
        logging.error(f"get_stats এরর: {e}")
        conn.close()
        return {'posted': 0}

# ============================================
# লগিং
# ============================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================
# বট ইনিশিয়ালাইজ
# ============================================

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# ============================================
# Telethon ক্লায়েন্ট
# ============================================

async def get_telethon_client():
    try:
        client = TelegramClient('bot_session', API_ID, API_HASH)
        await client.start()
        me = await client.get_me()
        logger.info(f"✅ Telethon লগইন সফল: {me.first_name}")
        return client
    except FloodWaitError as e:
        logger.warning(f"Flood wait: {e.seconds} সেকেন্ড অপেক্ষা করুন")
        await asyncio.sleep(e.seconds)
        return await get_telethon_client()
    except Exception as e:
        logger.error(f"Telethon লগইন ব্যর্থ: {e}")
        return None

# ============================================
# বট হ্যান্ডলার
# ============================================

@dp.message(Command("start"))
async def start_command(message: Message):
    stats = get_stats()
    interval = get_setting('post_interval') or DEFAULT_INTERVAL
    status = get_setting('bot_status') or 'active'
    first_run = get_setting('first_run') == 'true'
    current_caption = get_setting('global_caption') or DEFAULT_CAPTION
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 স্ট্যাটাস", callback_data="stats"),
            InlineKeyboardButton(text="⚙️ সেটিংস", callback_data="settings")
        ],
        [
            InlineKeyboardButton(text="📹 সব ভিডিও পোস্ট করুন", callback_data="post_all"),
            InlineKeyboardButton(text="🗑️ রিসেট করুন", callback_data="reset_all")
        ]
    ])
    
    await message.answer(
        f"🤖 <b>The Mindscape Auto-Poster Bot</b>\n\n"
        f"📊 <b>পরিসংখ্যান:</b>\n"
        f"• পোস্ট হয়েছে: {stats['posted']} টি\n"
        f"• স্ট্যাটাস: {'🟢 চালু' if status == 'active' else '🔴 বন্ধ'}\n"
        f"• {'🆕 প্রথমবার চালু' if first_run else '🔄 চলমান'}\n\n"
        f"⚙️ <b>সেটিংস:</b>\n"
        f"• সময় ব্যবধান: {interval} মিনিট\n"
        f"• ক্যাপশন: {current_caption}\n\n"
        f"📥 <b>স্টোরেজ চ্যানেল:</b> প্রাইভেট চ্যানেল\n"
        f"📤 <b>পোস্ট চ্যানেল:</b> {TARGET_CHANNEL}",
        reply_markup=keyboard
    )

@dp.message(Command("settings"))
async def settings_command(message: Message):
    interval = get_setting('post_interval') or DEFAULT_INTERVAL
    caption = get_setting('global_caption') or DEFAULT_CAPTION
    status = get_setting('bot_status') or 'active'
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⏰ সময় সেট করুন", callback_data="set_time"),
            InlineKeyboardButton(text="📝 ক্যাপশন সেট করুন", callback_data="set_caption")
        ],
        [
            InlineKeyboardButton(text="▶️ বট চালু করুন", callback_data="bot_on"),
            InlineKeyboardButton(text="⏹️ বট বন্ধ করুন", callback_data="bot_off")
        ],
        [
            InlineKeyboardButton(text="🔙 ব্যাক", callback_data="back")
        ]
    ])
    
    await message.answer(
        f"⚙️ <b>সেটিংস ম্যানেজার</b>\n\n"
        f"• সময় ব্যবধান: {interval} মিনিট\n"
        f"• গ্লোবাল ক্যাপশন: {caption}\n"
        f"• বট স্ট্যাটাস: {'🟢 চালু' if status == 'active' else '🔴 বন্ধ'}",
        reply_markup=keyboard
    )

@dp.message(Command("settime"))
async def set_time_command(message: Message):
    try:
        args = message.text.split()
        if len(args) < 2:
            await message.answer("❌ সঠিক ফরম্যাট: `/settime 15`")
            return
        minutes = int(args[1])
        if minutes < 1 or minutes > 60:
            await message.answer("❌ সময় ১ থেকে ৬০ মিনিটের মধ্যে হতে হবে!")
            return
        update_setting('post_interval', str(minutes))
        await message.answer(f"✅ সময় সেট করা হয়েছে: {minutes} মিনিট")
    except ValueError:
        await message.answer("❌ অনুগ্রহ করে একটি সংখ্যা দিন!")

@dp.message(Command("setcaption"))
async def set_caption_command(message: Message):
    try:
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.answer("❌ সঠিক ফরম্যাট: `/setcaption আপনার ক্যাপশন`")
            return
        caption = args[1]
        update_setting('global_caption', caption)
        await message.answer(f"✅ ক্যাপশন সেট করা হয়েছে!\n\n<code>{caption}</code>")
    except Exception as e:
        await message.answer(f"❌ এরর: {e}")

@dp.message(Command("postall"))
async def post_all_command(message: Message):
    await message.answer("⏳ সব ভিডিও পোস্ট করা শুরু হচ্ছে...")
    update_setting('last_message_id', '0')
    update_setting('first_run', 'true')
    count = await post_all_videos()
    await message.answer(f"✅ {count} টি ভিডিও পোস্ট করা হয়েছে!")

@dp.message(Command("reset"))
async def reset_command(message: Message):
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM posted_videos")
            cursor.execute("UPDATE bot_settings SET value = '0' WHERE key = 'last_message_id'")
            cursor.execute("UPDATE bot_settings SET value = 'true' WHERE key = 'first_run'")
            conn.commit()
            await message.answer("🗑️ সব পোস্ট হিসাব রিসেট করা হয়েছে!")
        except Exception as e:
            await message.answer(f"❌ রিসেট করতে ব্যর্থ: {e}")
        finally:
            conn.close()

# ============================================
# ইনলাইন বাটন কলব্যাক
# ============================================

@dp.callback_query()
async def handle_callback(callback_query: types.CallbackQuery):
    data = callback_query.data
    try:
        await callback_query.answer(cache_time=60)
    except:
        pass
    
    if data == 'stats':
        stats = get_stats()
        await callback_query.message.edit_text(f"📊 <b>বট পরিসংখ্যান</b>\n\n✅ পোস্ট হয়েছে: {stats['posted']} টি")
    elif data == 'settings':
        await settings_command(callback_query.message)
    elif data == 'post_all':
        await callback_query.message.answer("⏳ সব ভিডিও পোস্ট করা শুরু হচ্ছে...")
        update_setting('last_message_id', '0')
        update_setting('first_run', 'true')
        count = await post_all_videos()
        await callback_query.message.answer(f"✅ {count} টি ভিডিও পোস্ট করা হয়েছে!")
    elif data == 'reset_all':
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()
            try:
                cursor.execute("DELETE FROM posted_videos")
                cursor.execute("UPDATE bot_settings SET value = '0' WHERE key = 'last_message_id'")
                cursor.execute("UPDATE bot_settings SET value = 'true' WHERE key = 'first_run'")
                conn.commit()
                await callback_query.message.answer("🗑️ সব পোস্ট হিসাব রিসেট করা হয়েছে!")
            except Exception as e:
                await callback_query.message.answer(f"❌ রিসেট করতে ব্যর্থ: {e}")
            finally:
                conn.close()
    elif data == 'set_time':
        await callback_query.message.answer(f"⏰ <b>সময় সেট করুন</b>\n\nবর্তমান: {get_setting('post_interval') or DEFAULT_INTERVAL} মিনিট\n\nনতুন: <code>/settime 15</code>")
    elif data == 'set_caption':
        current = get_setting('global_caption') or DEFAULT_CAPTION
        await callback_query.message.answer(f"📝 <b>গ্লোবাল ক্যাপশন সেট করুন</b>\n\nবর্তমান:\n<code>{current}</code>\n\nনতুন: <code>/setcaption আপনার ক্যাপশন</code>")
    elif data == 'bot_on':
        update_setting('bot_status', 'active')
        await callback_query.message.answer("🟢 বট চালু করা হয়েছে!")
    elif data == 'bot_off':
        update_setting('bot_status', 'inactive')
        await callback_query.message.answer("🔴 বট বন্ধ করা হয়েছে!")
    elif data == 'back':
        await start_command(callback_query.message)

# ============================================
# সব ভিডিও পোস্ট করার ফাংশন
# ============================================

async def post_all_videos():
    try:
        status = get_setting('bot_status') or 'active'
        if status == 'inactive':
            return 0
        
        client = await get_telethon_client()
        if not client:
            logger.error("❌ Telethon ক্লায়েন্ট তৈরি করতে ব্যর্থ!")
            return 0
        
        channel = await client.get_entity(STORAGE_CHANNEL_ID)
        posted_count = 0
        global_caption = get_setting('global_caption') or DEFAULT_CAPTION
        
        logger.info("📥 চ্যানেলের সব ভিডিও খোঁজা হচ্ছে...")
        
        async for message in client.iter_messages(channel, limit=None):
            is_video = False
            file_id = None
            
            if message.video:
                is_video = True
                file_id = str(message.video.id)
            elif message.document and message.document.mime_type and message.document.mime_type.startswith('video/'):
                is_video = True
                file_id = str(message.document.id)
            
            if is_video and not is_video_posted(message.id):
                try:
                    file_path = await message.download_media()
                    if file_path:
                        caption_text = message.text or global_caption
                        await bot.send_video(
                            chat_id=TARGET_CHANNEL,
                            video=FSInputFile(file_path),
                            caption=caption_text,
                            supports_streaming=True
                        )
                        mark_video_posted(message.id, file_id)
                        posted_count += 1
                        logger.info(f"✅ ভিডিও পোস্ট করা হয়েছে (মেসেজ ID: {message.id})")
                        try:
                            os.remove(file_path)
                        except:
                            pass
                        await asyncio.sleep(1)
                except Exception as e:
                    logger.error(f"ভিডিও পোস্ট করতে ব্যর্থ (ID: {message.id}): {e}")
            
            last_id = get_setting('last_message_id') or '0'
            if int(message.id) > int(last_id):
                update_setting('last_message_id', str(message.id))
        
        update_setting('first_run', 'false')
        await client.disconnect()
        return posted_count
    except Exception as e:
        logger.error(f"ভিডিও পোস্ট করতে ব্যর্থ: {e}")
        return 0

# ============================================
# নতুন ভিডিও চেক করার ফাংশন
# ============================================

async def check_new_videos():
    try:
        status = get_setting('bot_status') or 'active'
        if status == 'inactive':
            return 0
        
        client = await get_telethon_client()
        if not client:
            logger.error("❌ Telethon ক্লায়েন্ট তৈরি করতে ব্যর্থ!")
            return 0
        
        channel = await client.get_entity(STORAGE_CHANNEL_ID)
        posted_count = 0
        global_caption = get_setting('global_caption') or DEFAULT_CAPTION
        last_id = int(get_setting('last_message_id') or '0')
        
        async for message in client.iter_messages(channel, limit=100, min_id=last_id):
            is_video = False
            file_id = None
            
            if message.video:
                is_video = True
                file_id = str(message.video.id)
            elif message.document and message.document.mime_type and message.document.mime_type.startswith('video/'):
                is_video = True
                file_id = str(message.document.id)
            
            if is_video and not is_video_posted(message.id):
                try:
                    file_path = await message.download_media()
                    if file_path:
                        caption_text = message.text or global_caption
                        await bot.send_video(
                            chat_id=TARGET_CHANNEL,
                            video=FSInputFile(file_path),
                            caption=caption_text,
                            supports_streaming=True
                        )
                        mark_video_posted(message.id, file_id)
                        posted_count += 1
                        logger.info(f"✅ নতুন ভিডিও পোস্ট করা হয়েছে (মেসেজ ID: {message.id})")
                        try:
                            os.remove(file_path)
                        except:
                            pass
                        await asyncio.sleep(1)
                except Exception as e:
                    logger.error(f"ভিডিও পোস্ট করতে ব্যর্থ (ID: {message.id}): {e}")
            
            if message.id > last_id:
                last_id = message.id
        
        update_setting('last_message_id', str(last_id))
        await client.disconnect()
        return posted_count
    except Exception as e:
        logger.error(f"নতুন ভিডিও চেক করতে ব্যর্থ: {e}")
        return 0

# ============================================
# শিডিউলার
# ============================================

async def scheduler():
    logger.info("⏰ শিডিউলার শুরু হয়েছে...")
    
    first_run = get_setting('first_run') == 'true'
    if first_run:
        logger.info("📥 প্রথমবার চালু, সব ভিডিও পোস্ট করা হচ্ছে...")
        count = await post_all_videos()
        logger.info(f"✅ {count} টি ভিডিও পোস্ট করা হয়েছে!")
        update_setting('first_run', 'false')
    
    while True:
        try:
            status = get_setting('bot_status') or 'active'
            if status == 'inactive':
                await asyncio.sleep(60)
                continue
            
            interval = int(get_setting('post_interval') or DEFAULT_INTERVAL)
            logger.info(f"⏳ {interval} মিনিট অপেক্ষা করছে...")
            await asyncio.sleep(interval * 60)
            
            logger.info("📥 নতুন ভিডিও চেক করা হচ্ছে...")
            posted = await check_new_videos()
            
            if posted > 0:
                logger.info(f"✅ {posted} টি নতুন ভিডিও পোস্ট করা হয়েছে!")
            else:
                logger.info("⏳ কোনো নতুন ভিডিও নেই")
        except Exception as e:
            logger.error(f"শিডিউলার এরর: {e}")
            await asyncio.sleep(60)

# ============================================
# বট চালু করুন
# ============================================

async def main():
    logger.info("🚀 বট চালু হচ্ছে...")
    init_db()
    
    if not get_setting('post_interval'):
        update_setting('post_interval', str(DEFAULT_INTERVAL))
    if not get_setting('global_caption'):
        update_setting('global_caption', DEFAULT_CAPTION)
    
    if os.path.exists('bot_session.session'):
        try:
            os.remove('bot_session.session')
            logger.info("🔄 পুরনো session ফাইল ডিলিট করা হয়েছে")
        except:
            pass
    
    logger.info("📱 Telethon লগইন হচ্ছে...")
    client = await get_telethon_client()
    if client:
        await client.disconnect()
        logger.info("✅ Telethon লগইন সফল!")
    else:
        logger.warning("⚠️ Telethon লগইন ব্যর্থ! রি-রান করুন")
    
    asyncio.create_task(scheduler())
    
    logger.info("✅ বট চালু হয়েছে!")
    logger.info(f"📥 স্টোরেজ চ্যানেল: {STORAGE_CHANNEL_ID}")
    logger.info(f"📤 টার্গেট চ্যানেল: {TARGET_CHANNEL}")
    logger.info(f"⏰ ইন্টারভাল: {get_setting('post_interval') or DEFAULT_INTERVAL} মিনিট")
    logger.info(f"📝 ক্যাপশন: {get_setting('global_caption') or DEFAULT_CAPTION}")
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())