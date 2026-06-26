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
ALLOWED_USERS = [YOUR_ID_HERE]   # ←←← Замени на свой Telegram ID

def is_allowed(user_id: int) -> bool:
    return user_id in ALLOWED_USERS

# ====================== ДАННЫЕ ======================
clients = {}
current_account = None
selected_chats = []      # [(chat_id или link, name), ...]
custom_chats = {}        # {name: link}

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
async def check_access(event: types.Message | types.CallbackQuery):
    user_id = event.from_user.id
    if not is_allowed(user_id):
        if isinstance(event, types.Message):
            await event.answer("⛔ У вас нет доступа к этому боту.")
        else:
            await event.answer("⛔ Доступ запрещён", show_alert=True)
        return False
    return True

# ====================== КОМАНДЫ ======================
@dp.message(Command("start"))
async def start(message: types.Message):
    if not await check_access(message): return
    await message.answer("🤖 **Приватный Spammer Bot**\nДоступ разрешён ✅", reply_markup=main_menu())

@dp.message(Command("myid"))
async def get_my_id(message: types.Message):
    await message.answer(f"🆔 Ваш ID: <code>{message.from_user.id}</code>", parse_mode="HTML")

# ====================== ЗАГРУЗКА СЕССИИ ======================
@dp.message(Command("upload_session"))
async def upload_session(message: types.Message):
    if not await check_access(message): return
    await message.answer("📤 Отправь .session файл")

@dp.message(F.document)
async def handle_session(message: types.Message):
    if not await check_access(message): return
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

# ====================== ДОБАВЛЕНИЕ ПО ССЫЛКЕ ======================
@dp.callback_query(F.data == "add_link")
async def add_link(callback: types.CallbackQuery, state: FSMContext):
    if not await check_access(callback): return
    await callback.message.edit_text("🔗 Отправь ссылку на чат или группу:")
    await state.set_state(SpammerStates.waiting_for_link)

@dp.message(SpammerStates.waiting_for_link)
async def process_link(message: types.Message, state: FSMContext):
    if not await check_access(message): return
    await state.update_data(link=message.text.strip())
    await message.answer("Как назвать этот чат?")
    await state.set_state(SpammerStates.waiting_for_name)

@dp.message(SpammerStates.waiting_for_name)
async def save_custom_chat(message: types.Message, state: FSMContext):
    if not await check_access(message): return
    name = message.text.strip()
    data = await state.get_data()
    custom_chats[name] = data['link']
    await message.answer(f"✅ Сохранено:\n{name}", reply_markup=main_menu())
    await state.clear()

# ====================== СПИСОК ЧАТОВ ======================
@dp.callback_query(F.data == "show_chats")
async def show_chats(callback: types.CallbackQuery):
    if not await check_access(callback): return
    if not current_account:
        return await callback.answer("Сначала выберите аккаунт!", show_alert=True)

    await callback.message.edit_text("⏳ Загружаю чаты...")

    try:
        client = clients[current_account]
        keyboard = []

        # Личные чаты
        keyboard.append([InlineKeyboardButton(text="👤 ЛИЧНЫЕ ЧАТЫ", callback_data="dummy")])
        async for dialog in client.get_dialogs(limit=15):
            chat = dialog.chat
            if chat.type == "private":
                status = "✅ " if any(x[0] == chat.id for x in selected_chats) else ""
                keyboard.append([InlineKeyboardButton(text=f"{status}{chat.first_name}", callback_data=f"select_{chat.id}")])

        # Групповые
        keyboard.append([InlineKeyboardButton(text="👥 ГРУППЫ И КАНАЛЫ", callback_data="dummy")])
        async for dialog in client.get_dialogs(limit=15):
            chat = dialog.chat
            if chat.type in ["group", "supergroup", "channel"]:
                status = "✅ " if any(x[0] == chat.id for x in selected_chats) else ""
                keyboard.append([InlineKeyboardButton(text=f"{status}{chat.title[:30]}", callback_data=f"select_{chat.id}")])

        # Сохранённые по ссылке
        if custom_chats:
            keyboard.append([InlineKeyboardButton(text="🔗 СОХРАНЁННЫЕ", callback_data="dummy")])
            for name in custom_chats:
                status = "✅ " if any(x[1] == name for x in selected_chats) else ""
                keyboard.append([InlineKeyboardButton(text=f"{status}🔗 {name}", callback_data=f"custom_{name}")])

        keyboard.append([InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")])

        await callback.message.edit_text(f"📋 Чаты (выбрано: {len(selected_chats)})", 
                                       reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}", reply_markup=main_menu())

# ... (остальные хендлеры select_chat, start_spam, infinite_spam и stop — оставь как в предыдущей версии)

# ====================== ЗАПУСК ======================
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())