import asyncio
import os
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram import Client
from pyrogram.errors import FloodWait
from dotenv import load_dotenv

load_dotenv()

API_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")

SESSIONS_DIR = "sessions"
os.makedirs(SESSIONS_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

current_client = None
selected_chats = []   # список выбранных chat_id
all_dialogs = []      # кэш всех диалогов

# ==================== СОСТОЯНИЯ ====================
class SpammerStates(StatesGroup):
    waiting_for_text = State()
    waiting_for_interval = State()

# ==================== КЛАВИАТУРЫ ====================
def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Мои чаты", callback_data="show_chats")],
        [InlineKeyboardButton(text="🚀 Начать рассылку", callback_data="start_spam")],
        [InlineKeyboardButton(text="🛑 Остановить", callback_data="stop_bot")]
    ])

# ==================== ХЕНДЛЕРЫ ====================
@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "🤖 **Pyrogram Spammer Bot**\n\n"
        "Загрузи .session файл командой /upload_session\n"
        "Или используй меню ниже 👇",
        reply_markup=main_menu()
    )

@dp.message(Command("upload_session"))
async def upload_session(message: types.Message):
    await message.answer("📤 Отправь мне `.session` файл Pyrogram")

@dp.message(F.document)
async def handle_session(message: types.Message):
    global current_client
    if not message.document.file_name.endswith('.session'):
        return await message.answer("❌ Нужен файл с расширением `.session`")

    file_path = os.path.join(SESSIONS_DIR, "user.session")
    file = await bot.get_file(message.document.file_id)
    await bot.download_file(file.file_path, file_path)

    await message.answer("✅ Сессия загружена. Подключаюсь...")

    try:
        current_client = Client(
            name="user",
            api_id=API_ID,
            api_hash=API_HASH,
            workdir=SESSIONS_DIR
        )
        await current_client.start()
        me = await current_client.get_me()
        await message.answer(f"✅ Успешно авторизовались как {me.first_name} (@{me.username})", 
                           reply_markup=main_menu())
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")

@dp.callback_query(F.data == "show_chats")
async def show_chats(callback: types.CallbackQuery):
    global all_dialogs
    if not current_client:
        return await callback.answer("Сначала загрузи сессию!", show_alert=True)

    await callback.message.edit_text("⏳ Загружаю список чатов...")

    all_dialogs.clear()
    keyboard = []

    async for dialog in current_client.get_dialogs(limit=40):
        chat = dialog.chat
        chat_id = chat.id
        title = chat.title or chat.first_name or "Private Chat"
        all_dialogs.append((chat_id, title))
        
        keyboard.append([InlineKeyboardButton(
            text=f"{'✅' if chat_id in selected_chats else ''} {title[:35]}",
            callback_data=f"select_{chat_id}"
        )])

    keyboard.append([InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")])

    await callback.message.edit_text(
        f"📋 Выберите чаты (нажмите для выбора/снятия):\n\n"
        f"Выбрано: {len(selected_chats)}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )

@dp.callback_query(F.data.startswith("select_"))
async def select_chat(callback: types.CallbackQuery):
    global selected_chats
    chat_id = int(callback.data.split("_")[1])

    if chat_id in selected_chats:
        selected_chats.remove(chat_id)
    else:
        selected_chats.append(chat_id)

    # Обновляем список
    await show_chats(callback)

@dp.callback_query(F.data == "start_spam")
async def start_spam(callback: types.CallbackQuery, state: FSMContext):
    if not selected_chats:
        return await callback.answer("Выберите хотя бы один чат!", show_alert=True)
    
    await callback.message.edit_text(
        f"✍️ Отправьте текст, который хотите разослать в {len(selected_chats)} чатов:"
    )
    await state.set_state(SpammerStates.waiting_for_text)

@dp.message(SpammerStates.waiting_for_text)
async def process_text(message: types.Message, state: FSMContext):
    await state.update_data(spam_text=message.text)
    await message.answer("⏱ Введите интервал между сообщениями в секундах (минимум 5 рекомендуется):")
    await state.set_state(SpammerStates.waiting_for_interval)

@dp.message(SpammerStates.waiting_for_interval)
async def process_interval(message: types.Message, state: FSMContext):
    try:
        interval = int(message.text)
        if interval < 1:
            raise ValueError
        data = await state.get_data()
        text = data['spam_text']
        
        await message.answer(f"🚀 **Запуск рассылки**\nЧатов: {len(selected_chats)}\nИнтервал: {interval} сек")
        await state.clear()
        asyncio.create_task(do_spam(message, text, interval))
    except:
        await message.answer("❌ Пожалуйста, введите число.")

async def do_spam(message: types.Message, text: str, interval: int):
    global current_client
    sent = 0
    for chat_id in selected_chats[:]:
        try:
            await current_client.send_message(chat_id, text)
            sent += 1
            await message.answer(f"✅ {sent}/{len(selected_chats)} → {chat_id}")
            await asyncio.sleep(interval)
        except FloodWait as e:
            await asyncio.sleep(e.value + 1)
        except Exception as e:
            await message.answer(f"❌ Ошибка {chat_id}: {e}")
            await asyncio.sleep(3)
    await message.answer(f"✅ **Рассылка завершена!**\nОтправлено: {sent}/{len(selected_chats)}")

@dp.callback_query(F.data == "stop_bot")
async def stop_bot(callback: types.CallbackQuery):
    await callback.answer("Остановлено")
    await callback.message.edit_text("🛑 Рассылка остановлена.\n\nИспользуйте меню:", reply_markup=main_menu())

@dp.callback_query(F.data == "main_menu")
async def back_to_menu(callback: types.CallbackQuery):
    await callback.message.edit_text("Главное меню:", reply_markup=main_menu())

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())