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

clients = {}           # {session_name: Client}
current_account = None
selected_targets = []  # [(chat_id, topic_id), ...]

class SpammerStates(StatesGroup):
    waiting_for_text = State()
    waiting_for_interval = State()

def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Мои чаты", callback_data="show_chats")],
        [InlineKeyboardButton(text="👤 Сменить аккаунт", callback_data="switch_account")],
        [InlineKeyboardButton(text="🚀 Запустить рассылку", callback_data="start_spam")],
        [InlineKeyboardButton(text="🛑 Остановить", callback_data="stop_bot")]
    ])

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("🤖 **Multi Spammer** с поддержкой тем", reply_markup=main_menu())

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
        await message.answer(f"❌ Ошибка подключения: {e}")

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

# ====================== ИСПРАВЛЕННЫЙ ЗАГРУЗ ЧАТОВ ======================
@dp.callback_query(F.data == "show_chats")
async def show_chats(callback: types.CallbackQuery):
    if not current_account or current_account not in clients:
        return await callback.answer("Сначала выберите аккаунт!", show_alert=True)

    await callback.message.edit_text("⏳ Загружаю чаты... (это может занять 5–15 сек)")

    try:
        client = clients[current_account]
        keyboard = []
        count = 0

        async for dialog in client.get_dialogs(limit=30):   # уменьшил лимит
            count += 1
            chat = dialog.chat
            title = (chat.title or chat.first_name or "Чат")[:35]
            chat_id = chat.id

            if chat.is_forum:
                keyboard.append([InlineKeyboardButton(text=f"📌 {title} (темы)", callback_data=f"forum_{chat_id}")])
            else:
                keyboard.append([InlineKeyboardButton(text=f"• {title}", callback_data=f"chat_{chat_id}")])

            if count >= 25:   # защита от слишком большого списка
                break

        keyboard.append([InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")])

        await callback.message.edit_text(
            f"📋 Доступные чаты (выбрано целей: {len(selected_targets)})",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
    except Exception as e:
        logging.error(e)
        await callback.message.edit_text(f"❌ Ошибка при загрузке чатов:\n{str(e)[:300]}\n\nПопробуй ещё раз.", 
                                       reply_markup=main_menu())

# Выбор обычного чата
@dp.callback_query(F.data.startswith("chat_"))
async def select_chat(callback: types.CallbackQuery):
    chat_id = int(callback.data.split("_")[1])
    if (chat_id, None) not in selected_targets:
        selected_targets.append((chat_id, None))
    await callback.answer("✅ Чат добавлен")
    await show_chats(callback)

# Показ тем
@dp.callback_query(F.data.startswith("forum_"))
async def show_forum_topics(callback: types.CallbackQuery):
    chat_id = int(callback.data.split("_")[1])
    await callback.message.edit_text("⏳ Загружаю темы...")

    try:
        client = clients[current_account]
        keyboard = []
        async for topic in client.get_forum_topics(chat_id, limit=15):
            keyboard.append([InlineKeyboardButton(
                text=topic.title[:45],
                callback_data=f"topic_{chat_id}_{topic.id}"
            )])
        
        keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="show_chats")])
        await callback.message.edit_text(f"📌 Темы чата", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    except Exception as e:
        await callback.message.edit_text(f"❌ Не удалось загрузить темы:\n{str(e)[:200]}")

@dp.callback_query(F.data.startswith("topic_"))
async def select_topic(callback: types.CallbackQuery):
    _, chat_id, topic_id = callback.data.split("_")
    target = (int(chat_id), int(topic_id))
    if target not in selected_targets:
        selected_targets.append(target)
    await callback.answer("✅ Тема добавлена")
    await callback.message.edit_text("Тема выбрана. Можешь выбрать ещё или запустить рассылку.", 
                                   reply_markup=main_menu())

# ====================== РАССЫЛКА ======================
@dp.callback_query(F.data == "start_spam")
async def start_spam(callback: types.CallbackQuery, state: FSMContext):
    if not selected_targets:
        return await callback.answer("Выберите хотя бы одну цель!", show_alert=True)
    if not current_account:
        return await callback.answer("Выберите аккаунт!", show_alert=True)

    await callback.message.edit_text("✍️ Введите текст для рассылки:")
    await state.set_state(SpammerStates.waiting_for_text)

@dp.message(SpammerStates.waiting_for_text)
async def process_text(message: types.Message, state: FSMContext):
    await state.update_data(spam_text=message.text)
    await message.answer("⏱ Интервал в секундах (например 60 = 1 минута):")
    await state.set_state(SpammerStates.waiting_for_interval)

@dp.message(SpammerStates.waiting_for_interval)
async def process_interval(message: types.Message, state: FSMContext):
    global current_spam_task, spam_task_running
    try:
        interval = max(int(message.text), 5)
        data = await state.get_data()
        text = data['spam_text']
        await state.clear()

        await message.answer(f"🚀 Рассылка запущена!\nЦелей: {len(selected_targets)}\nИнтервал: {interval} сек")
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
        for chat_id, topic_id in selected_targets[:]:
            if not spam_task_running: break
            try:
                await client.send_message(chat_id=chat_id, text=text, message_thread_id=topic_id)
                await message.answer(f"✅ → {chat_id} | тема: {topic_id or 'основная'}")
            except FloodWait as e:
                await asyncio.sleep(e.value)
            except Exception as e:
                await message.answer(f"❌ Ошибка {chat_id}: {str(e)[:100]}")
            await asyncio.sleep(interval)

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

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())