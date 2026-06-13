import os
import json
import asyncio
from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from datetime import datetime
import time

load_dotenv()

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
CHATS_FILE = "chats.json"
BROADCAST_FILE = "broadcast_status.json"

# Инициализация клиента
app = Client(
    name="my_account",
    api_id=API_ID,
    api_hash=API_HASH,
    workdir="./sessions"
)

# Глобальное состояние
broadcast_state = {
    "is_running": False,
    "current_chat_index": 0,
    "total_chats": 0,
    "sent": 0,
    "failed": 0,
}

# Хранилище данных
user_data = {
    "selected_chats": [],
    "broadcast_text": "",
    "interval": 5,  # интервал в секундах
    "mode": None,
}


def load_chats():
    """Загрузить сохраненные чаты"""
    if os.path.exists(CHATS_FILE):
        try:
            with open(CHATS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}


def save_chats(chats):
    """Сохранить чаты"""
    with open(CHATS_FILE, "w", encoding="utf-8") as f:
        json.dump(chats, f, ensure_ascii=False, indent=2)


def get_main_keyboard():
    """Главное меню"""
    keyboard = [
        [InlineKeyboardButton("📤 Создать рассылку", callback_data="new_broadcast")],
        [InlineKeyboardButton("💾 Добавить чат", callback_data="add_chat")],
        [InlineKeyboardButton("📋 Список чатов", callback_data="list_chats")],
        [InlineKeyboardButton("🗑 Удалить чат", callback_data="delete_chat")],
    ]
    return InlineKeyboardMarkup(keyboard)


@app.on_message(filters.private & filters.user(ADMIN_ID) & filters.command("start"))
async def start(client, message):
    """Стартовое меню"""
    await message.reply(
        "👋 **Telegram Broadcaster**\n\n"
        "Отправляй рассылки в свои чаты с интервалом.\n\n"
        "⚙️ Выбери действие:",
        reply_markup=get_main_keyboard(),
        parse_mode="markdown"
    )


@app.on_callback_query(filters.user(ADMIN_ID))
async def callback_handler(client, query: CallbackQuery):
    """Обработка кнопок"""
    data = query.data
    chats = load_chats()

    if data == "new_broadcast":
        await query.message.edit_text(
            "📤 **Выбери чаты для рассылки:**\n\n"
            "(Нажимай на чаты, потом 'Далее')",
            reply_markup=get_chat_selection_keyboard(chats)
        )
        user_data["mode"] = "selecting_chats"
        user_data["selected_chats"] = []

    elif data == "add_chat":
        await query.message.edit_text(
            "💾 **Добавить новый чат**\n\n"
            "Отправь ID чата или переши сообщение из чата.\n\n"
            "❌ /cancel - отмена",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀️ Назад", callback_data="back_menu")]
            ])
        )
        user_data["mode"] = "add_chat"

    elif data == "list_chats":
        if chats:
            text = "📋 **Твои чаты:**\n\n"
            for name, chat_id in chats.items():
                text += f"• {name}\n   ID: `{chat_id}`\n\n"
        else:
            text = "📋 **Нет сохраненных чатов**"
        
        await query.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀️ Назад", callback_data="back_menu")]
            ]),
            parse_mode="markdown"
        )

    elif data == "delete_chat":
        if chats:
            buttons = []
            for name in chats.keys():
                buttons.append([InlineKeyboardButton(f"🗑 {name}", callback_data=f"del_chat_{name}")])
            buttons.append([InlineKeyboardButton("◀️ Назад", callback_data="back_menu")])
            await query.message.edit_text(
                "🗑 **Выбери чат для удаления:**",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
        else:
            await query.answer("Нет чатов для удаления", show_alert=True)

    elif data.startswith("del_chat_"):
        chat_name = data.replace("del_chat_", "")
        if chat_name in chats:
            del chats[chat_name]
            save_chats(chats)
            await query.answer(f"✅ Чат '{chat_name}' удален")
        await query.message.edit_text(
            "✅ **Чат удален!**",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀️ Назад", callback_data="back_menu")]
            ])
        )

    elif data.startswith("chat_"):
        chat_id = data.replace("chat_", "")
        if chat_id in user_data["selected_chats"]:
            user_data["selected_chats"].remove(chat_id)
        else:
            user_data["selected_chats"].append(chat_id)
        await query.message.edit_reply_markup(
            reply_markup=get_chat_selection_keyboard(chats)
        )

    elif data == "next_broadcast":
        if user_data["selected_chats"]:
            await query.message.edit_text(
                "✍️ **Отправь текст для рассылки:**\n\n"
                "(Текст, фото или медиа)\n\n"
                "❌ /cancel - отмена",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("◀️ Назад", callback_data="new_broadcast")]
                ])
            )
            user_data["mode"] = "input_message"
        else:
            await query.answer("⚠️ Выбери хотя бы один чат", show_alert=True)

    elif data == "set_interval":
        await query.message.edit_text(
            "⏱ **Укажи интервал между сообщениями (в секундах):**\n\n"
            "例: 5, 10, 30 и т.д.\n\n"
            "❌ /cancel - отмена",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀️ Назад", callback_data="new_broadcast")]
            ])
        )
        user_data["mode"] = "input_interval"

    elif data == "confirm_broadcast":
        await query.message.edit_text(
            "⏱ **Укажи интервал в секундах:**\n\n"
            "Пример: 5 (5 сек между сообщениями)",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Отмена", callback_data="new_broadcast")]
            ])
        )
        user_data["mode"] = "input_interval"

    elif data == "back_menu":
        user_data["mode"] = None
        user_data["selected_chats"] = []
        await query.message.edit_text(
            "👋 **Главное меню**",
            reply_markup=get_main_keyboard()
        )


def get_chat_selection_keyboard(chats):
    """Клавиатура выбора чатов"""
    buttons = []
    for name, chat_id in chats.items():
        is_selected = chat_id in user_data["selected_chats"]
        emoji = "✅" if is_selected else "⬜"
        buttons.append([InlineKeyboardButton(f"{emoji} {name}", callback_data=f"chat_{chat_id}")])
    
    buttons.append([InlineKeyboardButton("➡️ Далее", callback_data="next_broadcast")])
    buttons.append([InlineKeyboardButton("◀️ Назад", callback_data="back_menu")])
    
    return InlineKeyboardMarkup(buttons)


@app.on_message(filters.private & filters.user(ADMIN_ID) & ~filters.command("start"))
async def message_handler(client, message):
    """Обработка текстовых сообщений"""
    
    if message.text and message.text.startswith("/cancel"):
        user_data["mode"] = None
        user_data["selected_chats"] = []
        await message.reply(
            "❌ Отменено",
            reply_markup=get_main_keyboard()
        )
        return

    chats = load_chats()

    # Режим добавления чата
    if user_data["mode"] == "add_chat":
        try:
            # Если это переслано сообщение
            if message.forward_from_chat:
                chat_id = str(message.forward_from_chat.id)
                chat_name = message.forward_from_chat.title or f"Chat_{chat_id}"
            else:
                # Иначе пытаемся парсить как ID
                chat_id = str(int(message.text))
                chat_name = f"Chat_{chat_id}"

            if chat_id not in chats.values():
                chats[chat_name] = chat_id
                save_chats(chats)
                user_data["mode"] = None
                
                await message.reply(
                    f"✅ Чат '{chat_name}' добавлен!",
                    reply_markup=get_main_keyboard()
                )
            else:
                await message.reply("⚠️ Этот чат уже добавлен!")
        except:
            await message.reply(
                "⚠️ Ошибка! Отправь ID чата или переши сообщение из чата."
            )

    # Режим ввода сообщения для рассылки
    elif user_data["mode"] == "input_message":
        user_data["broadcast_text"] = message
        
        # Создаем сообщение подтверждения
        keyboard = [
            [
                InlineKeyboardButton("✅ Далее", callback_data="confirm_broadcast"),
                InlineKeyboardButton("❌ Назад", callback_data="new_broadcast")
            ]
        ]
        
        preview_text = message.text if message.text else "(медиа)"
        await message.reply(
            f"📋 **Предпросмотр:**\n\n{preview_text}\n\n"
            f"Отправить в {len(user_data['selected_chats'])} чатов?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # Режим ввода интервала
    elif user_data["mode"] == "input_interval":
        try:
            interval = int(message.text)
            if interval < 1:
                await message.reply("⚠️ Интервал должен быть ≥ 1 секунде")
                return
            
            user_data["interval"] = interval
            
            # Показываем финальное подтверждение
            chat_count = len(user_data["selected_chats"])
            keyboard = [
                [
                    InlineKeyboardButton("✅ Начать рассылку", callback_data="start_broadcast"),
                    InlineKeyboardButton("❌ Отмена", callback_data="new_broadcast")
                ]
            ]
            
            await message.reply(
                f"✅ **Подтверждение рассылки:**\n\n"
                f"📤 Чатов: {chat_count}\n"
                f"⏱ Интервал: {interval} сек\n"
                f"📝 Текст: {user_data['broadcast_text'].text if user_data['broadcast_text'].text else '(медиа)'}\n\n"
                f"Все готово?",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            user_data["mode"] = None
        except:
            await message.reply(
                "⚠️ Введи число! Пример: 5, 10, 30"
            )


@app.on_callback_query(filters.user(ADMIN_ID))
async def handle_broadcast_start(client, query: CallbackQuery):
    """Начало рассылки"""
    if query.data == "start_broadcast":
        await query.message.edit_text("⏳ Рассылка начинается...")
        await send_broadcast(client, query.message)
        await query.answer("✅ Рассылка завершена!")


async def send_broadcast(client, message):
    """Отправка рассылки со всеми чатами и интервалом"""
    global broadcast_state
    
    broadcast_state["is_running"] = True
    broadcast_state["sent"] = 0
    broadcast_state["failed"] = 0
    broadcast_state["total_chats"] = len(user_data["selected_chats"])
    broadcast_state["current_chat_index"] = 0
    
    chats = load_chats()
    start_time = datetime.now()
    
    # Создаем статус сообщение
    status_msg = await message.reply(
        "⏳ **Рассылка в процессе...**\n\n"
        f"Начало: {start_time.strftime('%H:%M:%S')}"
    )
    
    for idx, chat_id in enumerate(user_data["selected_chats"]):
        try:
            if user_data["broadcast_text"].text:
                await client.send_message(int(chat_id), user_data["broadcast_text"].text)
            else:
                # Для медиа
                await client.forward_messages(int(chat_id), "me", user_data["broadcast_text"].message_id)
            
            broadcast_state["sent"] += 1
            broadcast_state["current_chat_index"] = idx + 1
            
            # Обновляем статус каждые 3 сообщения
            if (idx + 1) % 3 == 0 or (idx + 1) == broadcast_state["total_chats"]:
                await status_msg.edit_text(
                    f"⏳ **Рассылка в процессе...**\n\n"
                    f"Отправлено: {broadcast_state['sent']}/{broadcast_state['total_chats']}\n"
                    f"Ошибок: {broadcast_state['failed']}\n\n"
                    f"Начало: {start_time.strftime('%H:%M:%S')}\n"
                    f"Время: {(datetime.now() - start_time).total_seconds():.0f} сек"
                )
            
            # Интервал между сообщениями
            if idx < len(user_data["selected_chats"]) - 1:
                await asyncio.sleep(user_data["interval"])
                
        except Exception as e:
            print(f"❌ Ошибка при отправке в {chat_id}: {e}")
            broadcast_state["failed"] += 1

    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    # Финальное сообщение
    await status_msg.edit_text(
        f"✅ **Рассылка завершена!**\n\n"
        f"📤 Отправлено: {broadcast_state['sent']}\n"
        f"❌ Ошибок: {broadcast_state['failed']}\n"
        f"⏱ Время: {duration:.0f} сек\n"
        f"🕐 Начало: {start_time.strftime('%H:%M:%S')}\n"
        f"🕑 Конец: {end_time.strftime('%H:%M:%S')}\n\n"
        f"Интервал был: {user_data['interval']} сек",
        reply_markup=get_main_keyboard()
    )
    
    # Сброс состояния
    user_data["selected_chats"] = []
    user_data["broadcast_text"] = ""
    user_data["interval"] = 5
    broadcast_state["is_running"] = False


async def main():
    """Главная функция"""
    print("🚀 Бот запущен...")
    os.makedirs("./sessions", exist_ok=True)
    async with app:
        print("✅ Подключено к Telegram")
        await app.idle()


if __name__ == "__main__":
    asyncio.run(main())
