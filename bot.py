import asyncio
import os
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from pyrogram import Client
from pyrogram.errors import FloodWait
from dotenv import load_dotenv

load_dotenv()

# ==================== НАСТРОЙКИ ====================
API_TOKEN = os.getenv("BOT_TOKEN")          # Токен твоего бота
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")

# Папка для хранения сессий
SESSIONS_DIR = "sessions"
os.makedirs(SESSIONS_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ==================== СОСТОЯНИЯ ====================
class SpammerStates(StatesGroup):
    waiting_for_session = State()
    waiting_for_chats = State()
    waiting_for_text = State()
    waiting_for_interval = State()

# Глобальные переменные для текущей сессии (для простоты — один пользователь)
current_client = None
selected_chats = []

# ==================== ХЕНДЛЕРЫ ====================
@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "👋 Привет! Это бот для рассылки с Pyrogram сессии.\n\n"
        "Команды:\n"
        "/upload_session — загрузить .session файл\n"
        "/chats — показать чаты\n"
        "/spam — начать рассылку\n"
        "/stop — остановить"
    )

@dp.message(Command("upload_session"))
async def upload_session(message: types.Message, state: FSMContext):
    await message.answer("📤 Отправь мне файл .session (Pyrogram)")
    await state.set_state(SpammerStates.waiting_for_session)

@dp.message(F.document, SpammerStates.waiting_for_session)
async def handle_session_file(message: types.Message, state: FSMContext):
    global current_client
    if not message.document.file_name.endswith('.session'):
        return await message.answer("❌ Нужен именно .session файл!")

    file = await bot.get_file(message.document.file_id)
    file_path = os.path.join(SESSIONS_DIR, "user.session")
    
    await bot.download_file(file.file_path, file_path)
    await message.answer("✅ Сессия загружена!")

    # Инициализируем Pyrogram client
    try:
        current_client = Client(
            name="user",
            api_id=API_ID,
            api_hash=API_HASH,
            session_string=None,  # будет использовать файл
            workdir=SESSIONS_DIR
        )
        await current_client.start()
        await message.answer("🔑 Успешно авторизовались по сессии!")
        await state.clear()
    except Exception as e:
        await message.answer(f"❌ Ошибка авторизации: {str(e)}")
        await state.clear()

@dp.message(Command("chats"))
async def get_chats(message: types.Message):
    global current_client
    if not current_client:
        return await message.answer("❌ Сначала загрузи сессию (/upload_session)")

    try:
        dialogs = []
        async for dialog in current_client.get_dialogs(limit=50):
            dialogs.append(f"{dialog.chat.id} | {dialog.chat.title or dialog.chat.first_name or 'Private'}")
        
        text = "📋 Последние чаты:\n\n" + "\n".join(dialogs[:30])
        await message.answer(text[:4000] + "\n\nОтправь ID чатов через запятую для рассылки (/spam)")
    except Exception as e:
        await message.answer(f"Ошибка: {e}")

@dp.message(Command("spam"))
async def start_spam(message: types.Message, state: FSMContext):
    if not current_client:
        return await message.answer("Загрузи сессию сначала!")
    await message.answer("Отправь ID чатов через запятую (например: -100123456789,123456789)")
    await state.set_state(SpammerStates.waiting_for_chats)

@dp.message(SpammerStates.waiting_for_chats)
async def process_chats(message: types.Message, state: FSMContext):
    global selected_chats
    try:
        selected_chats = [int(x.strip()) for x in message.text.split(',')]
        await message.answer(f"✅ Выбрано чатов: {len(selected_chats)}\n\nТеперь отправь текст для рассылки")
        await state.set_state(SpammerStates.waiting_for_text)
    except:
        await message.answer("❌ Неверный формат ID")

@dp.message(SpammerStates.waiting_for_text)
async def process_text(message: types.Message, state: FSMContext):
    text = message.text
    await message.answer("⏱ Укажи интервал между сообщениями в секундах (минимум 1):")
    await state.update_data(spam_text=text)
    await state.set_state(SpammerStates.waiting_for_interval)

@dp.message(SpammerStates.waiting_for_interval)
async def process_interval(message: types.Message, state: FSMContext):
    try:
        interval = int(message.text)
        if interval < 1:
            raise ValueError
        data = await state.get_data()
        spam_text = data['spam_text']
        
        await message.answer(f"🚀 Запускаю рассылку в {len(selected_chats)} чатов с интервалом {interval} сек...")
        await state.clear()
        
        await do_spam(message, spam_text, interval)
    except:
        await message.answer("❌ Введи число секунд")

async def do_spam(message: types.Message, text: str, interval: int):
    global current_client
    sent = 0
    for chat_id in selected_chats:
        try:
            await current_client.send_message(chat_id, text)
            sent += 1
            await message.answer(f"✅ Отправлено в {chat_id} ({sent}/{len(selected_chats)})")
            await asyncio.sleep(interval)
        except FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception as e:
            await message.answer(f"❌ Ошибка в {chat_id}: {e}")
    await message.answer(f"✅ Рассылка завершена! Отправлено: {sent}")

@dp.message(Command("stop"))
async def stop(message: types.Message):
    global current_client
    if current_client:
        await current_client.stop()
        current_client = None
    await message.answer("🛑 Остановлено")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())