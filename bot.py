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

# ====================== ПРИВАТНОСТЬ ======================
ALLOWED_USERS = [8237163079]   # ←←← СЮДА ВСТАВЬ СВОЙ TELEGRAM ID

def is_allowed(user_id: int) -> bool:
    return user_id in ALLOWED_USERS

# ====================== ОСТАЛЬНОЕ ======================
clients = {}
current_account = None
selected_chats = []
custom_chats = {}   # {name: link}

class SpammerStates(StatesGroup):
    waiting_for_text = State()
    waiting_for_interval = State()
    waiting_for_link = State()
    waiting_for_name = State()

def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Мои чаты", callback_data="show_chats")],
        [InlineKeyboardButton(text="➕ Добавить по ссылке", callback_data="add_link")],
        [InlineKeyboardButton(text="👤 Сменить аккаунт", callback_data="switch_account")],
        [InlineKeyboardButton(text="🚀 Запустить рассылку", callback_data="start_spam")],
        [InlineKeyboardButton(text="🛑 Остановить", callback_data="stop_bot")]
    ])

# ====================== ЗАЩИТА ======================
@dp.message()
async def check_access(message: types.Message):
    if not is_allowed(message.from_user.id):
        return await message.answer("⛔ У вас нет доступа к этому боту.")
    # Если доступ есть — продолжаем обработку дальше

# ====================== КОМАНДЫ ======================
@dp.message(Command("start"))
async def start(message: types.Message):
    if not is_allowed(message.from_user.id):
        return
    await message.answer("🤖 **Приватный Spammer Bot**\n\nДоступ разрешён.", reply_markup=main_menu())

@dp.message(Command("myid"))
async def get_my_id(message: types.Message):
    await message.answer(f"🆔 Ваш ID: <code>{message.from_user.id}</code>", parse_mode="HTML")

# ====================== СЕССИИ ======================
@dp.message(Command("upload_session"))
async def upload_session(message: types.Message):
    if not is_allowed(message.from_user.id): return
    await message.answer("📤 Отправь .session файл")

@dp.message(F.document)
async def handle_session(message: types.Message):
    if not is_allowed(message.from_user.id): return
    # ... (код загрузки сессии без изменений) ...
    global current_account
    if not message.document.file_name.endswith('.session'):
        return await message.answer("❌ Нужен .session файл")

    session_name = message.document.file_name.replace(".session", "")
    file_path = os.path.join(SESSIONS_DIR, f"{session_name}.session")

    await bot.download_file((await bot.get_file(message.document.file_id)).file_path, file_path)

    try:
        client = Client(session_name, api_id=API_ID, api_hash=API_HASH, workdir=SESSIONS_DIR)
        await client.start()
        me = await client.get_me()
        clients[session_name] = client
        current_account = session_name
        await message.answer(f"✅ Аккаунт добавлен: {me.first_name}", reply_markup=main_menu())
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

# Остальные хендлеры (show_chats, add_link, рассылка и т.д.) тоже нужно защитить

# Для удобства можно добавить декоратор, но чтобы не усложнять — просто добавь проверку в каждый важный хендлер.

# ====================== ПРИМЕР ЗАЩИТЫ ДЛЯ ОДНОГО ХЕНДЛЕРА ======================
@dp.callback_query(F.data == "show_chats")
async def show_chats(callback: types.CallbackQuery):
    if not is_allowed(callback.from_user.id):
        return await callback.answer("Доступ запрещён", show_alert=True)
    # ... остальной код show_chats ...

# То же самое нужно добавить во все callback_query и message хендлеры.

# Чтобы не писать везде вручную, вот **лучший способ**:

# Замени начало файла на это:

# ====================== УЛУЧШЕННАЯ ЗАЩИТА (рекомендую) ======================
async def is_allowed_middleware(message: types.Message | types.CallbackQuery):
    user_id = message.from_user.id if isinstance(message, types.Message) else message.from_user.id
    if not is_allowed(user_id):
        if isinstance(message, types.Message):
            await message.answer("⛔ У вас нет доступа к этому боту.")
        else:
            await message.answer("⛔ Доступ запрещён", show_alert=True)
        return False
    return True

# Потом в каждом хендлере в начале добавляй:
# if not await is_allowed_middleware(message): return