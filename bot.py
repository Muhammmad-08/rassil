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
from pyrogram.errors import FloodWait, UserIsBlocked, ChatWriteForbidden
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

current_client: Client = None
selected_chats = []
all_dialogs = []

class SpammerStates(StatesGroup):
    waiting_for_text = State()
    waiting_for_interval = State()

def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Мои чаты", callback_data="show_chats")],
        [InlineKeyboardButton(text="🚀 Начать рассылку", callback_data="start_spam")],
        [InlineKeyboardButton(text="🛑 Остановить", callback_data="stop_bot")]
    ])

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("🤖 **Pyrogram Spammer Bot** готов к работе", reply_markup=main_menu())

@dp.message(Command("upload_session"))
async def upload_session(message: types.Message):
    await message.answer("📤 Отправь .session файл")

@dp.message(F.document)
async def handle_session(message: types.Message):
    global current_client
    if not message.document.file_name.endswith('.session'):
        return await message.answer("❌ Нужен .session файл")

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
        await message.answer(f"✅ Авторизация успешна: {me.first_name}", reply_markup=main_menu())
    except Exception as e:
        await message.answer(f"❌ Ошибка подключения: {e}")

@dp.callback_query(F.data == "show_chats")
async def show_chats(callback: types.CallbackQuery):
    global all_dialogs
    if not current_client:
        return await callback.answer("Сначала загрузи сессию!", show_alert=True)

    await callback.message.edit_text("⏳ Загружаю чаты...")

    all_dialogs.clear()
    keyboard = []
    async for dialog in current_client.get_dialogs(limit=50):
        chat = dialog.chat
        chat_id = chat.id
        title = (chat.title or chat.first_name or "Личный чат")[:40]
        all_dialogs.append((chat_id, title))
        
        status = "✅ " if chat_id in selected_chats else ""
        keyboard.append([InlineKeyboardButton(
            text=f"{status}{title}",
            callback_data=f"select_{chat_id}"
        )])

    keyboard.append([InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")])

    await callback.message.edit_text(
        f"📋 Выберите чаты для рассылки\nВыбрано: **{len(selected_chats)}**",
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
    
    await show_chats(callback)  # обновляем список

@dp.callback_query(F.data == "start_spam")
async def start_spam(callback: types.CallbackQuery, state: FSMContext):
    if not selected_chats:
        return await callback.answer("Выберите хотя бы один чат!", show_alert=True)
    
    await callback.message.edit_text(
        f"✍️ Отправьте текст для рассылки в **{len(selected_chats)}** чатов:"
    )
    await state.set_state(SpammerStates.waiting_for_text)

@dp.message(SpammerStates.waiting_for_text)
async def process_text(message: types.Message, state: FSMContext):
    await state.update_data(spam_text=message.html_text)  # сохраняем с HTML
    await message.answer("⏱ Введите интервал между сообщениями в секундах (рекомендую 10+):")
    await state.set_state(SpammerStates.waiting_for_interval)

@dp.message(SpammerStates.waiting_for_interval)
async def process_interval(message: types.Message, state: FSMContext):
    try:
        interval = int(message.text)
        if interval < 1:
            interval = 5
        data = await state.get_data()
        text = data.get('spam_text')
        
        await message.answer(f"🚀 **Рассылка запущена!**\nЧатов: {len(selected_chats)}\nИнтервал: {interval} сек")
        await state.clear()
        
        # Запускаем рассылку
        asyncio.create_task(spam_task(message, text, interval))
        
    except:
        await message.answer("❌ Введите число секунд.")

async def spam_task(message: types.Message, text: str, interval: int):
    """Отдельная задача для рассылки"""
    global current_client
    if not current_client:
        await message.answer("❌ Сессия потеряна")
        return

    sent = 0
    total = len(selected_chats)
    
    for i, chat_id in enumerate(selected_chats[:], 1):   # копия списка
        try:
            await current_client.send_message(chat_id, text, parse_mode="HTML")
            sent += 1
            await message.answer(f"✅ {i}/{total} | Отправлено в {chat_id}")
        except FloodWait as e:
            await message.answer(f"⏳ FloodWait {e.value} сек...")
            await asyncio.sleep(e.value)
        except (UserIsBlocked, ChatWriteForbidden):
            await message.answer(f"❌ Чат {chat_id} заблокировал бота")
        except Exception as e:
            await message.answer(f"❌ Ошибка в {chat_id}: {str(e)[:100]}")
        await asyncio.sleep(interval)

    await message.answer(f"🎉 **Рассылка завершена!**\nОтправлено: {sent}/{total}", reply_markup=main_menu())

@dp.callback_query(F.data == "stop_bot")
async def stop_bot(callback: types.CallbackQuery):
    await callback.answer("Рассылка остановлена", show_alert=True)
    await callback.message.edit_text("🛑 Остановлено", reply_markup=main_menu())

@dp.callback_query(F.data == "main_menu")
async def back_to_menu(callback: types.CallbackQuery):
    await callback.message.edit_text("Главное меню", reply_markup=main_menu())

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())