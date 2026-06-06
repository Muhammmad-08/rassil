from pyrogram import Client, filters
from pyrogram.types import Message
import os

# ==================== НАСТРОЙКИ ====================
API_ID = int(os.getenv("API_ID", "39326700"))
API_HASH = os.getenv("API_HASH", "81153f77544e5232414ef2143bea3d4f")
BOT_TOKEN = os.getenv("BOT_TOKEN", "8957798155:AAG3W0ubABZ8bE3rzAHJohT4vymev7Blbm8")

app = Client(
    name="my_controller_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workdir="/tmp"  # Railway — файловая система временная, пишем в /tmp
)

# ==================== КОМАНДЫ ====================

@app.on_message(filters.command("start"))
async def start(client, message: Message):
    await message.reply(
        "👋 **Привет!** Я твой управляющий бот.\n\n"
        "Отправляй команды, чтобы я выполнял действия.\n\n"
        "Используй /help для списка команд."
    )


@app.on_message(filters.command("send") & filters.private)
async def send_message(client, message: Message):
    try:
        parts = message.text.split(maxsplit=2)  # ["/send", "@username", "текст"]

        if len(parts) < 3:
            await message.reply(
                "❌ Использование:\n"
                "`/send @username текст`\n"
                "`/send +7xxxxxxxxxx текст`"
            )
            return

        target = parts[1]
        text = parts[2]

        user = await client.get_users(target)
        await client.send_message(user.id, text)

        await message.reply(f"✅ Сообщение отправлено **{user.mention}**")

    except Exception as e:
        await message.reply(f"❌ Ошибка: `{str(e)}`")


@app.on_message(filters.command("me"))
async def my_info(client, message: Message):
    me = await client.get_me()
    await message.reply(
        f"**🤖 Информация о боте**\n\n"
        f"**Имя:** {me.first_name}\n"
        f"**Username:** @{me.username}\n"
        f"**ID:** `{me.id}`"
    )


@app.on_message(filters.command("help"))
async def help_cmd(client, message: Message):
    await message.reply(
        "**🛠 Доступные команды:**\n\n"
        "`/send @username текст` — отправить сообщение\n"
        "`/send +7xxxxxxxxxx текст` — отправить по номеру\n"
        "`/me` — информация о боте\n"
        "`/help` — список команд"
    )


# ==================== ЗАПУСК ====================
if __name__ == "__main__":
    print("✅ Бот запускается...")
    app.run()
