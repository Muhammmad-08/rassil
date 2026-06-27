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

# Очистка API_ID и API_HASH
raw_api_id = os.getenv("API_ID", "").strip().replace('"', '').replace("'", "")
API_ID = int(raw_api_id) if raw_api_id.isdigit() else None
API_HASH = os.getenv("API_HASH", "").strip().replace('"', '').replace("'", "")

SESSIONS_DIR = "sessions"
os.makedirs(SESSIONS_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO)

if not API_ID or not API_HASH or not API_TOKEN:
    logging.error("❌ Проверьте переменные окружения BOT_TOKEN, API_ID и API_HASH!")

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
# Формат selected_chats: [(chat_id, topic_id, "Название чата/темы"), ...]
selected_chats = []      

class SpammerStates(StatesGroup):
    waiting_for_text = State()
    waiting_for_msg_interval = State()
    waiting_for_loop_interval = State()

def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📁 Загрузить .session", callback_data="upload_session")],
        [InlineKeyboardButton(text="📋 Выбрать темы/чаты", callback_data="show_chats")],
        [InlineKeyboardButton(text="🚀 Запустить рассылку", callback_data="start_spam")],
        [InlineKeyboardButton(text="🛑 Остановить", callback_data="stop_bot")]
    ])

# ====================== СТАРТ ======================
@dp.message(Command("start"))
async def start(message: types.Message):
    if not is_allowed(message.from_user.id):
        return await message.answer("⛔ У вас нет доступа.")

    await message.answer(
        "🤖 **Spammer Bot**\n\n"
        "Используйте меню для загрузки сессий и настройки рассылки.",
        reply_markup=main_menu()
    )

# ====================== ЗАГРУЗКА .SESSION ======================
@dp.callback_query(F.data == "upload_session")
async def upload_session_callback(callback: types.CallbackQuery):
    if not is_allowed(callback.from_user.id): return
    await callback.message.edit_text("📤 Отправьте файл `.session` документа в этот чат.")

@dp.message(F.document)
async def handle_session(message: types.Message):
    if not is_allowed(message.from_user.id): return
    global current_account
    if not message.document.file_name.endswith('.session'):
        return await message.answer("❌ Нужен файл с расширением `.session`")

    session_name = message.document.file_name.replace(".session", "")
    file_path = os.path.join(SESSIONS_DIR, f"{session_name}.session")

    await bot.download_file((await bot.get_file(message.document.file_id)).file_path, file_path)

    try:
        client = Client(session_name, api_id=API_ID, api_hash=API_HASH, workdir=SESSIONS_DIR)
        await client.connect()
        me = await client.get_me()
        clients[session_name] = client
        current_account = session_name
        await message.answer(f"✅ Аккаунт успешно загружен: {me.first_name}", reply_markup=main_menu())
    except Exception as e:
        await message.answer(f"❌ Ошибка инициализации сессии: {e}")

# ====================== ВЫБОР ЧАТОВ И ТЕМ ======================
@dp.callback_query(F.data == "show_chats")
async def show_chats(callback: types.CallbackQuery):
    if not is_allowed(callback.from_user.id): return
    if not current_account:
        return await callback.answer("Сначала загрузите аккаунт!", show_alert=True)

    await callback.message.edit_text("⏳ Получаю список доступных чатов и тем (форумов)...")

    try:
        client = clients[current_account]
        keyboard = []
        
        async for dialog in client.get_dialogs(limit=20):
            chat = dialog.chat
            
            if chat.is_forum:
                try:
                    async for forum_topic in client.get_forum_topics(chat.id, limit=15):
                        topic_id = forum_topic.id
                        topic_title = forum_topic.title
                        display_name = f"💬 {chat.title[:15]} -> {topic_title[:15]}"
                        
                        status = "✅ " if any(x[0] == chat.id and x[1] == topic_id for x in selected_chats) else ""
                        
                        keyboard.append([InlineKeyboardButton(
                            text=f"{status}{display_name}", 
                            callback_data=f"top_{chat.id}_{topic_id}"
                        )])
                except Exception:
                    pass
            else:
                title = chat.title or chat.first_name or "Чат"
                display_name = f"👤 {title[:30]}"
                status = "✅ " if any(x[0] == chat.id and x[1] is None for x in selected_chats) else ""
                
                keyboard.append([InlineKeyboardButton(
                    text=f"{status}{display_name}", 
                    callback_data=f"ch_{chat.id}"
                )])

        keyboard.append([InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")])
        await callback.message.edit_text(f"📋 Доступные направления (Выбрано: {len(selected_chats)})", 
                                       reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка получения списка: {e}", reply_markup=main_menu())

@dp.callback_query(F.data.startswith("ch_"))
async def select_regular_chat(callback: types.CallbackQuery):
    if not is_allowed(callback.from_user.id): return
    chat_id = int(callback.data.split("_")[1])
    target = (chat_id, None, "Обычный чат")
    existing = [x for x in selected_chats if x[0] == chat_id and x[1] is None]
    if not existing:
        selected_chats.append(target)
        await callback.answer("✅ Чат добавлен")
    else:
        selected_chats.remove(existing[0])
        await callback.answer("❌ Чат убран")
    await show_chats(callback)

@dp.callback_query(F.data.startswith("top_"))
async def select_forum_topic(callback: types.CallbackQuery):
    if not is_allowed(callback.from_user.id): return
    parts = callback.data.split("_")
    chat_id = int(parts[1])
    topic_id = int(parts[2])
    target = (chat_id, topic_id, f"Тема {topic_id}")
    existing = [x for x in selected_chats if x[0] == chat_id and x[1] == topic_id]
    if not existing:
        selected_chats.append(target)
        await callback.answer("✅ Тема добавлена")
    else:
        selected_chats.remove(existing[0])
        await callback.answer("❌ Тема убрана")
    await show_chats(callback)

# ====================== РАССЫЛКА И ТАЙМЕРЫ ======================
spam_task_running = False
current_spam_task = None

@dp.callback_query(F.data == "start_spam")
async def start_spam(callback: types.CallbackQuery, state: FSMContext):
    if not is_allowed(callback.from_user.id): return
    if not selected_chats:
        return await callback.answer("Сначала выберите хотя бы один чат или тему!", show_alert=True)
    await callback.message.edit_text("✍️ Введите текст для рассылки:")
    await state.set_state(SpammerStates.waiting_for_text)

@dp.message(SpammerStates.waiting_for_text)
async def process_text(message: types.Message, state: FSMContext):
    if not is_allowed(message.from_user.id): return
    await state.update_data(spam_text=message.text)
    await message.answer("⏱ **Интервал 1:** Пауза *между чатами* (в секундах):")
    await state.set_state(SpammerStates.waiting_for_msg_interval)

@dp.message(SpammerStates.waiting_for_msg_interval)
async def process_msg_interval(message: types.Message, state: FSMContext):
    if not is_allowed(message.from_user.id): return
    global current_spam_task, spam_task_running
    try:
        msg_int = max(int(message.text), 1)  # Минимум 1 секунда
        await state.update_data(msg_interval=msg_int)
        
        # Если выбрано 2 или более чатов, просим вторую паузу
        if len(selected_chats) >= 2:
            await message.answer("🔄 **Интервал 2:** Пауза *между кругами* рассылки (после обхода всех чатов, в секундах):")
            await state.set_state(SpammerStates.waiting_for_loop_interval)
        else:
            # Если выбран всего 1 чат, то пауза между кругами не нужна, сразу запускаем
            data = await state.get_data()
            text = data['spam_text']
            await state.clear()
            
            await message.answer(
                f"🚀 **Рассылка запущена (для 1 чата)!**\n\n"
                f"⏱ Пауза между отправками: {msg_int} сек."
            )
            current_spam_task = asyncio.create_task(infinite_spam(message, text, msg_int, loop_interval=0))
            spam_task_running = True
    except:
        await message.answer("❌ Введите корректное число секунд.")

@dp.message(SpammerStates.waiting_for_loop_interval)
async def process_loop_interval(message: types.Message, state: FSMContext):
    if not is_allowed(message.from_user.id): return
    global current_spam_task, spam_task_running
    try:
        loop_int = max(int(message.text), 0)
        data = await state.get_data()
        text = data['spam_text']
        msg_int = data['msg_interval']
        await state.clear()
        
        await message.answer(
            f"🚀 **Рассылка запущена!**\n\n"
            f"⏱ Между чатами: {msg_int} сек.\n"
            f"🔄 Между кругами: {loop_int} сек."
        )
        current_spam_task = asyncio.create_task(infinite_spam(message, text, msg_int, loop_int))
        spam_task_running = True
    except:
        await message.answer("❌ Введите корректное число секунд.")

async def infinite_spam(message: types.Message, text: str, msg_interval: int, loop_interval: int):
    global spam_task_running
    client = clients[current_account]
    
    while spam_task_running:
        await message.answer("🔄 Начинаю круг рассылки по списку...")
        
        for index, (chat_id, topic_id, name) in enumerate(selected_chats):
            if not spam_task_running: break
            try:
                if topic_id is not None:
                    await client.send_message(chat_id, text, reply_to_message_id=topic_id)
                else:
                    await client.send_message(chat_id, text)
                
                await message.answer(f"✅ Отправлено -> {name}")
            except FloodWait as e:
                await message.answer(f"⏳ Поймали флудвейт от Telegram, ждем {e.value} сек.")
                await asyncio.sleep(e.value)
            except Exception as e:
                await message.answer(f"❌ Ошибка в {name}: {str(e)[:60]}")
            
            # Делаем паузу между чатами, кроме самого последнего чата в списке (после него будет пауза между кругами)
            if index < len(selected_chats) - 1:
                await asyncio.sleep(msg_interval)
            
        if not spam_task_running: break
        
        # Если выбрано больше 1 чата и задана пауза между кругами
        if len(selected_chats) >= 2 and loop_interval > 0:
            await message.answer(f"💤 Все чаты пройдены. Пауза перед новым кругом {loop_interval} сек.")
            await asyncio.sleep(loop_interval)
        else:
            # Если чат один, то он просто ждет заданный интервал и шлет снова
            await asyncio.sleep(msg_interval)

# ====================== ОСТАНОВКА И НАВИГАЦИЯ ======================
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
    await callback.message.edit_text("Главное меню управления:", reply_markup=main_menu())

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
