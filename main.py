import os
import asyncio
import random
from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.types import Message

load_dotenv()

# ==================== НАСТРОЙКИ ====================
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID"))
# ================================================

# Userbot клиент
user = Client("user_session", api_id=API_ID, api_hash=API_HASH)

# Control Bot клиент
bot = Client(
    "control_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# Keep-alive для бесплатных хостингов
async def keep_alive():
    while True:
        try:
            await asyncio.sleep(300)  # каждые 5 минут
            await bot.send_message(OWNER_ID, "🟢 Userbot работает...")
        except:
            pass

# ===================== КОМАНДЫ =====================

@bot.on_message(filters.command("send") & filters.private & filters.user(OWNER_ID))
async def send_msg(_, message: Message):
    try:
        args = message.text.split(maxsplit=2)
        if len(args) < 3:
            return await message.reply("❌ `/send <chat_id> <текст>`")
        
        chat_id = args[1]
        text = args[2]
        
        await asyncio.sleep(random.uniform(1.5, 3.5))  # человеческая задержка
        await user.send_message(chat_id, text)
        await message.reply(f"✅ Отправлено → `{chat_id}`")
    except Exception as e:
        await message.reply(f"❌ Ошибка: {e}")


@bot.on_message(filters.command("sendall") & filters.private & filters.user(OWNER_ID))
async def send_all(_, message: Message):
    try:
        args = message.text.split(maxsplit=2)
        if len(args) < 3:
            return await message.reply("❌ `/sendall <chat1,chat2,...> <текст>`")
        
        chats = [c.strip() for c in args[1].split(",")]
        text = args[2]
        success = 0

        for chat in chats:
            try:
                await asyncio.sleep(random.uniform(2, 5))
                await user.send_message(chat, text)
                success += 1
            except:
                pass

        await message.reply(f"✅ Успешно: {success}/{len(chats)}")
    except Exception as e:
        await message.reply(f"❌ {e}")


@bot.on_message(filters.command("chats") & filters.private & filters.user(OWNER_ID))
async def get_chats(_, message: Message):
    await message.reply("⏳ Загружаю чаты...")
    dialogs = []
    async for dialog in user.get_dialogs(limit=25):
        chat = dialog.chat
        name = chat.title or chat.first_name or "No Name"
        dialogs.append(f"• {name} | `{chat.id}`")
    
    text = "📋 **Ваши чаты:**\n\n" + "\n".join(dialogs)
    await message.reply(text)


@bot.on_message(filters.command("help") & filters.private & filters.user(OWNER_ID))
async def help_cmd(_, message: Message):
    await message.reply("""
**Команды:**

`/send <id или @username> текст`
`/sendall @user1,@group2 текст`
`/chats` — список чатов
`/help` — помощь
    """)


# ===================== ЗАПУСК =====================
async def main():
    print("🚀 Запуск Userbot + Control Bot...")
    await user.start()
    await bot.start()
    print("✅ Бот успешно запущен!")
    
    # Keep-alive
    asyncio.create_task(keep_alive())
    
    await asyncio.Future()  # бесконечный запуск

if __name__ == "__main__":
    asyncio.run(main())
