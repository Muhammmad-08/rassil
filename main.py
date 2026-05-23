import os
import asyncio
import random
import sys
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

print("🚀 Начинаем запуск...")

# Userbot клиент
user = Client(
    "user_session",
    api_id=API_ID,
    api_hash=API_HASH,
    device_model="Render",
    system_version="Linux",
    app_version="1.0"
)

# Control Bot
bot = Client(
    "control_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

async def keep_alive():
    while True:
        await asyncio.sleep(300)
        try:
            await bot.send_message(OWNER_ID, "🟢 Userbot работает на Render")
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
        await asyncio.sleep(random.uniform(1.5, 3.5))
        await user.send_message(chat_id, text)
        await message.reply(f"✅ Отправлено в `{chat_id}`")
    except Exception as e:
        await message.reply(f"❌ Ошибка: {e}")

@bot.on_message(filters.command("sendall") & filters.private & filters.user(OWNER_ID))
async def send_all(_, message: Message):
    try:
        args = message.text.split(maxsplit=2)
        if len(args) < 3:
            return await message.reply("❌ `/sendall <chat1,chat2> <текст>`")
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
        await message.reply(f"✅ Отправлено в {success}/{len(chats)} чатов")
    except Exception as e:
        await message.reply(f"❌ {e}")

@bot.on_message(filters.command(["chats", "list"]) & filters.private & filters.user(OWNER_ID))
async def get_chats(_, message: Message):
    await message.reply("⏳ Загружаю список чатов...")
    try:
        dialogs = []
        async for dialog in user.get_dialogs(limit=20):
            chat = dialog.chat
            name = chat.title or chat.first_name or chat.username or "Без названия"
            dialogs.append(f"• {name} | `{chat.id}`")
        text = "📋 **Ваши чаты:**\n\n" + "\n".join(dialogs)
        await message.reply(text)
    except Exception as e:
        await message.reply(f"❌ Ошибка при загрузке чатов: {e}")

@bot.on_message(filters.command("help") & filters.private & filters.user(OWNER_ID))
async def help_cmd(_, message: Message):
    await message.reply("""
**Доступные команды:**

`/send <@username или id> <текст>`
`/sendall <@user1,@group2> <текст>`
`/chats` — список чатов
`/help` — это сообщение
    """)

# ===================== ЗАПУСК =====================
async def main():
    print("🔄 Запуск user сессии...")
    await user.start()
    print("✅ Userbot успешно авторизован!")

    print("🔄 Запуск control бота...")
    await bot.start()
    print("✅ Control Bot запущен!")

    asyncio.create_task(keep_alive())
    print("🟢 Всё работает! Ожидаем команды...")

    await asyncio.Future()  # держим процесс живым

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"💥 Критическая ошибка: {e}")
        sys.exit(1)