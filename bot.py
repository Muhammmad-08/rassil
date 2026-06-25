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

clients = {}                    # {session_name: Client}
current_account = None
selected_chats = []             # список chat_id
custom_chats = {}               # {custom_name: chat_link или chat_id}

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

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("🤖 **Spammer Bot** (простая версия)", reply_markup=main_menu())

# ====================== СЕССИИ ======================
@dp.message(Command("upload_session"))
async def upload_session(message: types.Message):
    await message.answer("📤 Отправь .session файл")

@dp.message(F.document)
async def handle_session(message: types.Message):
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

@dp.callback_query(F.data == "switch_account")
async def switch_account(callback: types.CallbackQuery):
    if not clients:
        return await callback.answer("Нет аккаунтов", show_alert=True)
    kb = [[InlineKeyboardButton(text=name, callback_data=f"select_acc_{name}")] for name in clients]
    await callback.message.edit_text("Выберите аккаунт:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("select_acc_"))
async def select_account(callback: types.CallbackQuery):
    global current_account
    current_account = callback.data.split("_")[-1]
    await callback.answer(f"✓ {current_account}")
    await callback.message.edit_text(f"Текущий аккаунт: {current_account}", reply_markup=main_menu())

# ====================== ДОБАВЛЕНИЕ ПО ССЫЛКЕ ======================
@dp.callback_query(F.data == "add_link")
async def add_link(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🔗 Отправь ссылку на чат (t.me/ или +...):")
    await state.set_state(SpammerStates.waiting_for_link)

@dp.message(SpammerStates.waiting_for_link)
async def process_link(message: types.Message, state: FSMContext):
    link = message.text.strip()
    await state.update_data(link=link)
    await message.answer("Как назвать этот чат? (удобное имя)")
    await state.set_state(SpammerStates.waiting_for_name)

@dp.message(SpammerStates.waiting_for_name)
async def save_custom_chat(message: types.Message, state: FSMContext):
    name = message.text.strip()
    data = await state.get_data()
    link = data['link']
    custom_chats[name] = link
    await message.answer(f"✅ Чат сохранён:\nНазвание: {name}\nСсылка: {link}", reply_markup=main_menu())
    await state.clear()

# ====================== СПИСОК ЧАТОВ ======================
@dp.callback_query(F.data == "show_chats")
async def show_chats(callback: types.CallbackQuery):
    if not current_account:
        return await callback.answer("Сначала выберите аккаунт!", show_alert=True)

    await callback.message.edit_text("⏳ Загружаю чаты...")

    try:
        client = clients[current_account]
        keyboard = []

        # Личные чаты
        keyboard.append([InlineKeyboardButton(text="👤 ЛИЧНЫЕ ЧАТЫ", callback_data="dummy")])
        async for dialog in client.get_dialogs(limit=20):
            chat = dialog.chat
            if chat.type in ["private", "bot"]:
                status = "✅ " if chat.id in [x for x, _ in selected_chats if isinstance(x, int)] else ""
                keyboard.append([InlineKeyboardButton(
                    text=f"{status}{chat.first_name or chat.title}",
                    callback_data=f"select_{chat.id}"
                )])

        # Групповые чаты
        keyboard.append([InlineKeyboardButton(text="👥 ГРУППОВЫЕ ЧАТЫ", callback_data="dummy")])
        async for dialog in client.get_dialogs(limit=20):
            chat = dialog.chat
            if chat.type in ["group", "supergroup", "channel"]:
                status = "✅ " if chat.id in [x for x, _ in selected_chats if isinstance(x, int)] else ""
                keyboard.append([InlineKeyboardButton(
                    text=f"{status}{chat.title[:35]}",
                    callback_data=f"select_{chat.id}"
                )])

        # Сохранённые по ссылке
        if custom_chats:
            keyboard.append([InlineKeyboardButton(text="🔗 СОХРАНЁННЫЕ ПО ССЫЛКЕ", callback_data="dummy")])
            for name, link in custom_chats.items():
                keyboard.append([InlineKeyboardButton(text=f"🔗 {name}", callback_data=f"custom_{name}")])

        keyboard.append([InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")])

        await callback.message.edit_text(
            f"📋 Чаты\nВыбрано: {len(selected_chats)}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
    except Exception as e:
        await callback.message.edit_text(f"Ошибка загрузки: {e}", reply_markup=main_menu())

@dp.callback_query(F.data.startswith("select_"))
async def select_chat(callback: types.CallbackQuery):
    chat_id = int(callback.data.split("_")[1])
    if chat_id not in [x for x, _ in selected_chats]:
        selected_chats.append((chat_id, None))
        await callback.answer("✅ Добавлен")
    else:
        selected_chats.remove((chat_id, None))
        await callback.answer("❌ Убран")
    await show_chats(callback)

@dp.callback_query(F.data.startswith("custom_"))
async def select_custom(callback: types.CallbackQuery):
    name = callback.data.split("_", 1)[1]
    link = custom_chats[name]
    # Сохраняем как (link, name) — позже будем разрешать
    if (link, name) not in selected_chats:
        selected_chats.append((link, name))
        await callback.answer("✅ Добавлен по ссылке")
    else:
        selected_chats.remove((link, name))
        await callback.answer("❌ Убран")
    await show_chats(callback)

# ====================== РАССЫЛКА ======================
@dp.callback_query(F.data == "start_spam")
async def start_spam(callback: types.CallbackQuery, state: FSMContext):
    if not selected_chats:
        return await callback.answer("Выберите хотя бы один чат!", show_alert=True)
    
    await callback.message.edit_text("✍️ Введите текст для рассылки:")
    await state.set_state(SpammerStates.waiting_for_text)

@dp.message(SpammerStates.waiting_for_text)
async def process_text(message: types.Message, state: FSMContext):
    await state.update_data(spam_text=message.text)
    await message.answer("⏱ Интервал в секундах (например 60):")
    await state.set_state(SpammerStates.waiting_for_interval)

@dp.message(SpammerStates.waiting_for_interval)
async def process_interval(message: types.Message, state: FSMContext):
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

spam_task_running = False
current_spam_task = None

async def infinite_spam(message: types.Message, text: str, interval: int):
    global spam_task_running
    client = clients[current_account]
    while spam_task_running:
        for target, name in selected_chats[:]:
            if not spam_task_running: break
            try:
                if isinstance(target, str):  # это ссылка
                    chat = await client.get_chat(target)
                    await client.send_message(chat.id, text)
                    await message.answer(f"✅ → {name or target}")
                else:  # chat_id
                    await client.send_message(target, text)
                    await message.answer(f"✅ → {target}")
            except FloodWait as e:
                await asyncio.sleep(e.value)
            except Exception as e:
                await message.answer(f"❌ Ошибка {name or target}: {str(e)[:80]}")
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
    await callback.message.edit_text("Главное меню:", reply_markup=main_menu())

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())