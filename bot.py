import asyncio
import os
import logging
import random
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram import Client
from pyrogram.errors import FloodWait, SessionPasswordNeeded
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
ALLOWED_USERS = [8237163079]   # Твой Telegram ID

def is_allowed(user_id: int) -> bool:
    return user_id in ALLOWED_USERS

# ====================== ДАННЫЕ ======================
clients = {}
current_account = None
selected_chats = []      # [(chat_id или link, name), ...]
custom_chats = {}        # {name: link}

class AuthStates(StatesGroup):
    waiting_for_phone = State()
    waiting_for_code = State()
    waiting_for_password = State()

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

# ====================== СТАРТ ======================
@dp.message(Command("start"))
async def start(message: types.Message):
    if not is_allowed(message.from_user.id):
        return await message.answer("⛔ У вас нет доступа к этому боту.")

    await message.answer(
        "🤖 **Spammer Bot**\n\n"
        "Выберите способ входа:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📱 Войти по номеру телефона", callback_data="login_phone")],
            [InlineKeyboardButton(text="📤 Загрузить .session файл", callback_data="upload_session")]
        ])
    )

# ====================== ВХОД ПО НОМЕРУ ======================
@dp.callback_query(F.data == "login_phone")
async def login_phone(callback: types.CallbackQuery, state: FSMContext):
    if not is_allowed(callback.from_user.id): return
    await callback.message.edit_text("📱 Отправьте номер телефона:\n`+79123456789`", parse_mode="Markdown")
    await state.set_state(AuthStates.waiting_for_phone)

@dp.message(AuthStates.waiting_for_phone)
async def process_phone(message: types.Message, state: FSMContext):
    if not is_allowed(message.from_user.id): return
    phone = message.text.strip()
    session_name = f"user_{random.randint(10000,99999)}"

    await message.answer("⏳ Отправляю код...")

    try:
        client = Client(session_name, api_id=API_ID, api_hash=API_HASH, workdir=SESSIONS_DIR)
        await client.connect()
        await client.send_code(phone)

        await state.update_data(client=client, session_name=session_name, phone=phone)
        await message.answer("🔢 Введите код, который пришёл в Telegram или SMS:")
        await state.set_state(AuthStates.waiting_for_code)
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
        await state.clear()

@dp.message(AuthStates.waiting_for_code)
async def process_code(message: types.Message, state: FSMContext):
    if not is_allowed(message.from_user.id): return
    data = await state.get_data()
    client = data['client']
    session_name = data['session_name']

    try:
        await client.sign_in(data['phone'], message.text.strip())
        me = await client.get_me()
        clients[session_name] = client
        global current_account
        current_account = session_name

        await message.answer(f"✅ Успешный вход!\nАккаунт: {me.first_name}", reply_markup=main_menu())
        await state.clear()
    except SessionPasswordNeeded:
        await message.answer("🔑 Введите двухфакторный пароль:")
        await state.set_state(AuthStates.waiting_for_password)
    except Exception as e:
        await message.answer(f"❌ Неверный код: {e}")

@dp.message(AuthStates.waiting_for_password)
async def process_password(message: types.Message, state: FSMContext):
    if not is_allowed(message.from_user.id): return
    data = await state.get_data()
    client = data['client']
    session_name = data['session_name']

    try:
        await client.check_password(message.text.strip())
        me = await client.get_me()
        clients[session_name] = client
        global current_account
        current_account = session_name
        await message.answer(f"✅ Успешный вход!\nАккаунт: {me.first_name}", reply_markup=main_menu())
        await state.clear()
    except Exception as e:
        await message.answer(f"❌ Неверный пароль: {e}")

# ====================== ЗАГРУЗКА .SESSION ======================
@dp.callback_query(F.data == "upload_session")
async def upload_session_callback(callback: types.CallbackQuery):
    if not is_allowed(callback.from_user.id): return
    await callback.message.edit_text("📤 Отправьте файл `.session`")

@dp.message(F.document)
async def handle_session(message: types.Message):
    if not is_allowed(message.from_user.id): return
    global current_account
    if not message.document.file_name.endswith('.session'):
        return await message.answer("❌ Нужен файл `.session`")

    session_name = message.document.file_name.replace(".session", "")
    file_path = os.path.join(SESSIONS_DIR, f"{session_name}.session")

    await bot.download_file((await bot.get_file(message.document.file_id)).file_path, file_path)

    try:
        client = Client(session_name, api_id=API_ID, api_hash=API_HASH, workdir=SESSIONS_DIR)
        await client.start()
        me = await client.get_me()
        clients[session_name] = client
        current_account = session_name
        await message.answer(f"✅ Аккаунт загружен: {me.first_name}", reply_markup=main_menu())
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

# ====================== ОСТАЛЬНЫЕ ФУНКЦИИ (упрощённые) ======================
@dp.callback_query(F.data == "show_chats")
async def show_chats(callback: types.CallbackQuery):
    if not is_allowed(callback.from_user.id): return
    if not current_account:
        return await callback.answer("Сначала войдите в аккаунт!", show_alert=True)

    await callback.message.edit_text("⏳ Загружаю чаты...")

    try:
        client = clients[current_account]
        keyboard = []
        async for dialog in client.get_dialogs(limit=30):
            chat = dialog.chat
            title = chat.title or chat.first_name or "Чат"
            status = "✅ " if any(x[0] == chat.id for x in selected_chats) else ""
            keyboard.append([InlineKeyboardButton(text=f"{status}{title[:40]}", callback_data=f"select_{chat.id}")])

        if custom_chats:
            for name in custom_chats:
                status = "✅ " if any(x[1] == name for x in selected_chats) else ""
                keyboard.append([InlineKeyboardButton(text=f"{status}🔗 {name}", callback_data=f"custom_{name}")])

        keyboard.append([InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")])
        await callback.message.edit_text(f"📋 Чаты (выбрано: {len(selected_chats)})", 
                                       reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}", reply_markup=main_menu())

@dp.callback_query(F.data.startswith("select_"))
async def select_chat(callback: types.CallbackQuery):
    if not is_allowed(callback.from_user.id): return
    chat_id = int(callback.data.split("_")[1])
    target = (chat_id, None)
    if target not in selected_chats:
        selected_chats.append(target)
        await callback.answer("✅ Добавлен")
    else:
        selected_chats.remove(target)
        await callback.answer("❌ Убран")
    await show_chats(callback)

@dp.callback_query(F.data.startswith("custom_"))
async def select_custom(callback: types.CallbackQuery):
    if not is_allowed(callback.from_user.id): return
    name = callback.data.split("_", 1)[1]
    link = custom_chats[name]
    target = (link, name)
    if target not in selected_chats:
        selected_chats.append(target)
        await callback.answer("✅ Добавлен")
    else:
        selected_chats.remove(target)
        await callback.answer("❌ Убран")
    await show_chats(callback)

# ====================== РАССЫЛКА ======================
spam_task_running = False
current_spam_task = None

@dp.callback_query(F.data == "start_spam")
async def start_spam(callback: types.CallbackQuery, state: FSMContext):
    if not is_allowed(callback.from_user.id): return
    if not selected_chats:
        return await callback.answer("Выберите хотя бы один чат!", show_alert=True)
    await callback.message.edit_text("✍️ Введите текст для рассылки:")
    await state.set_state(SpammerStates.waiting_for_text)

@dp.message(SpammerStates.waiting_for_text)
async def process_text(message: types.Message, state: FSMContext):
    if not is_allowed(message.from_user.id): return
    await state.update_data(spam_text=message.text)
    await message.answer("⏱ Интервал в секундах:")
    await state.set_state(SpammerStates.waiting_for_interval)

@dp.message(SpammerStates.waiting_for_interval)
async def process_interval(message: types.Message, state: FSMContext):
    if not is_allowed(message.from_user.id): return
    global current_spam_task, spam_task_running
    try:
        interval = max(int(message.text), 5)
        data = await state.get_data()
        text = data['spam_text']
        await state.clear()
        await message.answer(f"🚀 Рассылка запущена!\nИнтервал: {interval} сек")
        current_spam_task = asyncio.create_task(infinite_spam(message, text, interval))
        spam_task_running = True
    except:
        await message.answer("❌ Введите число.")

async def infinite_spam(message: types.Message, text: str, interval: int):
    global spam_task_running
    client = clients[current_account]
    while spam_task_running:
        for target, name in selected_chats[:]:
            if not spam_task_running: break
            try:
                if isinstance(target, str):
                    chat = await client.get_chat(target)
                    await client.send_message(chat.id, text)
                else:
                    await client.send_message(target, text)
                await message.answer(f"✅ → {name or target}")
            except FloodWait as e:
                await asyncio.sleep(e.value)
            except Exception as e:
                await message.answer(f"❌ Ошибка: {str(e)[:100]}")
            await asyncio.sleep(interval)

# ====================== ОСТАНОВКА ======================
@dp.message(Command("stop"))
@dp.callback_query(F.data == "stop_bot")
async def stop_spam_handler(event):
    global spam_task_running, current_spam_task
    spam_task_running = False
    if current_spam_task:
        current_spam_task.cancel()
        current_spam_task = None
    text = "🛑 Рассылка остановлена."
    if isinstance(event, types.CallbackQuery):
        await event.answer("Остановлено", show_alert=True)
        await event.message.edit_text(text, reply_markup=main_menu())
    else:
        await event.answer(text, reply_markup=main_menu())

@dp.callback_query(F.data == "main_menu")
async def back_to_menu(callback: types.CallbackQuery):
    if not is_allowed(callback.from_user.id): return
    await callback.message.edit_text("Главное меню:", reply_markup=main_menu())

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())