import asyncio
import os
import logging
import time
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram import Client
from pyrogram.enums import ChatType
from pyrogram.errors import FloodWait, UsernameInvalid, PeerIdInvalid
from dotenv import load_dotenv

load_dotenv()

API_TOKEN = os.getenv("BOT_TOKEN")

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
selected_chats = []       # [(chat_id, topic_id, "Название")]
target_users = []         # Список загруженных юзернеймов для ЛС

class SpammerStates(StatesGroup):
    waiting_for_text = State()
    waiting_for_msg_interval = State()
    waiting_for_loop_interval = State()
    
    # Стейты для рассылки в ЛС
    waiting_for_users = State()
    waiting_for_pm_text = State()
    waiting_for_pm_interval = State()
    waiting_for_pm_loop_interval = State()

def main_menu():
    # Проверяем, загружен ли сейчас аккаунт, чтобы динамически менять текст
    account_status = f" Аккаунт: {current_account}" if current_account else "📁 Загрузить .session"
    
    buttons = [
        [InlineKeyboardButton(text=account_status, callback_data="upload_session")],
        [InlineKeyboardButton(text="👥 Выбрать Группы/Темы", callback_data="show_chats")],
        [InlineKeyboardButton(text="👤 Рассылка по Юзерам (ЛС)", callback_data="menu_users")],
        [InlineKeyboardButton(text="🚀 Запустить рассылку в чаты", callback_data="start_spam")]
    ]
    
    # Если аккаунт загружен, показываем кнопку для его удаления/выхода
    if current_account:
        buttons.append([InlineKeyboardButton(text="❌ Завершить (удалить) сессию", callback_data="delete_session")])
        
    buttons.append([InlineKeyboardButton(text="🛑 Остановить всё", callback_data="stop_bot")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ====================== СТАРТ ======================
@dp.message(Command("start"))
async def start(message: types.Message):
    if not is_allowed(message.from_user.id): return
    await message.answer("🤖 **Spammer Bot**\n\nУправляйте рассылкой в чаты/темы или по списку пользователей через меню.", reply_markup=main_menu())

# ====================== ЗАГРУЗКА .SESSION ======================
@dp.callback_query(F.data == "upload_session")
async def upload_session_callback(callback: types.CallbackQuery):
    if not is_allowed(callback.from_user.id): return
    await callback.message.edit_text("📤 Отправьте файл `.session` документом в этот чат.")

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

# ====================== УДАЛЕНИЕ / ВЫХОД ИЗ СЕССИИ ======================
@dp.callback_query(F.data == "delete_session")
async def delete_session_handler(callback: types.CallbackQuery):
    if not is_allowed(callback.from_user.id): return
    global current_account, spam_task_running, current_spam_task
    
    if not current_account:
        return await callback.answer("Нет активной сессии для удаления!", show_alert=True)
    
    await callback.message.edit_text("⏳ Завершаем сессию в Telegram и удаляем файл...")
    
    # 1. Сначала принудительно останавливаем спам, если он запущен
    spam_task_running = False
    if current_spam_task:
        current_spam_task.cancel()
        current_spam_task = None
        
    try:
        client = clients[current_account]
        
        # 2. Вызываем логаут. Telegram аннулирует сессию, а Pyrogram сотрет .session файл
        await client.log_out()
        
        # 3. Очищаем данные в боте
        del clients[current_account]
        old_account = current_account
        current_account = None
        selected_chats.clear() # Очищаем выбранные чаты, так как они были привязаны к аккаунту
        
        await callback.message.answer(f"✅ Сессия `{old_account}` успешно завершена на сервере и удалена из бота!", reply_markup=main_menu())
    except Exception as e:
        # Резервный случай: если логаут не сработал (например сессия уже была дохлая), 
        # просто удаляем файл вручную и чистим память
        file_path = os.path.join(SESSIONS_DIR, f"{current_account}.session")
        if os.path.exists(file_path):
            os.remove(file_path)
            
        if current_account in clients:
            del clients[current_account]
            
        current_account = None
        selected_chats.clear()
        await callback.message.answer(f"⚠️ Ошибка при мягком выходе, сессия удалена принудительно: {e}", reply_markup=main_menu())

# ====================== ВЫБОР ИСКЛЮЧИТЕЛЬНО ГРУПП ======================
@dp.callback_query(F.data == "show_chats")
async def show_chats(callback: types.CallbackQuery):
    if not is_allowed(callback.from_user.id): return
    if not current_account:
        return await callback.answer("Сначала загрузите аккаунт!", show_alert=True)

    await callback.message.edit_text("⏳ Получаю список групп...")
    try:
        client = clients[current_account]
        keyboard = []
        
        async for dialog in client.get_dialogs(limit=40):
            chat = dialog.chat
            
            # ФИЛЬТР: Берем ТОЛЬКО группы и супергруппы (Каналы и ЛС пропускаем)
            if chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
                continue
                
            is_forum_chat = getattr(chat, "is_forum", False)
            if is_forum_chat:
                try:
                    async for forum_topic in client.get_forum_topics(chat.id, limit=10):
                        topic_id = forum_topic.id
                        display_name = f"💬 {chat.title[:12]} -> {forum_topic.title[:12]}"
                        status = "✅ " if any(x[0] == chat.id and x[1] == topic_id for x in selected_chats) else ""
                        keyboard.append([InlineKeyboardButton(text=f"{status}{display_name}", callback_data=f"top_{chat.id}_{topic_id}")])
                except Exception:
                    is_forum_chat = False

            if not is_forum_chat:
                display_name = f"👥 {chat.title[:25]}"
                status = "✅ " if any(x[0] == chat.id and x[1] is None for x in selected_chats) else ""
                keyboard.append([InlineKeyboardButton(text=f"{status}{display_name}", callback_data=f"ch_{chat.id}")])

        keyboard.append([InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")])
        await callback.message.edit_text(f"📋 Выберите группы (Выбрано тем/чатов: {len(selected_chats)})", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}", reply_markup=main_menu())

@dp.callback_query(F.data.startswith("ch_"))
async def select_regular_chat(callback: types.CallbackQuery):
    if not is_allowed(callback.from_user.id): return
    chat_id = int(callback.data.split("_")[1])
    target = (chat_id, None, "Группа")
    existing = [x for x in selected_chats if x[0] == chat_id and x[1] is None]
    if not existing: selected_chats.append(target)
    else: selected_chats.remove(existing[0])
    await show_chats(callback)

@dp.callback_query(F.data.startswith("top_"))
async def select_forum_topic(callback: types.CallbackQuery):
    if not is_allowed(callback.from_user.id): return
    parts = callback.data.split("_")
    chat_id, topic_id = int(parts[1]), int(parts[2])
    target = (chat_id, topic_id, f"Тема {topic_id}")
    existing = [x for x in selected_chats if x[0] == chat_id and x[1] == topic_id]
    if not existing: selected_chats.append(target)
    else: selected_chats.remove(existing[0])
    await show_chats(callback)

# ====================== МОДУЛЬ РАССЫЛКИ ПО ЮЗЕРАМ (ЛС) ======================
@dp.callback_query(F.data == "menu_users")
async def menu_users(callback: types.CallbackQuery):
    if not is_allowed(callback.from_user.id): return
    text = f"👤 **Управление списком пользователей для ЛС**\n\nЗагружено юзеров: `{len(target_users)}`"
    kb = [
        [InlineKeyboardButton(text="📥 Загрузить список (@юз)", callback_data="import_users")],
        [InlineKeyboardButton(text="🚀 Запустить рассылку в ЛС", callback_data="start_pm_spam")],
        [InlineKeyboardButton(text="🗑 Очистить список", callback_data="clear_users")],
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")]
    ]
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "clear_users")
async def clear_users(callback: types.CallbackQuery):
    global target_users
    target_users.clear()
    await callback.answer("Список юзеров очищен")
    await menu_users(callback)

@dp.callback_query(F.data == "import_users")
async def import_users_cmd(callback: types.CallbackQuery, state: FSMContext):
    if not is_allowed(callback.from_user.id): return
    await callback.message.edit_text("✏️ Отправьте список юзернеймов (через запятую, пробел или столбиком).\nПример: `@user1 @user2, user3`")
    await state.set_state(SpammerStates.waiting_for_users)

@dp.message(SpammerStates.waiting_for_users)
async def process_users_list(message: types.Message, state: FSMContext):
    if not is_allowed(message.from_user.id): return
    global target_users
    raw_text = message.text.replace(",", " ").replace("\n", " ")
    parts = raw_text.split(" ")
    
    cleaned = []
    for p in parts:
        p = p.strip().replace("@", "")
        if p and len(p) >= 3:
            cleaned.append(p)
            
    target_users = list(set(cleaned)) # Удаляем дубликаты
    
    await state.clear()
    user_list_str = "\n".join([f"• @{u}" for u in target_users[:30]])
    if len(target_users) > 30:
        user_list_str += f"\n...и еще {len(target_users) - 30} пользователей."
        
    await message.answer(f"✅ **Анализ завершен!**\nУспешно найдено уникальных юзеров: `{len(target_users)}`\n\nСписок:\n{user_list_str}", reply_markup=main_menu())

# ====================== ЛОГИЧНЫЕ ТАЙМЕРЫ (РАССЫЛКА В ГРУППЫ) ======================
spam_task_running = False
current_spam_task = None

@dp.callback_query(F.data == "start_spam")
async def start_spam(callback: types.CallbackQuery, state: FSMContext):
    if not is_allowed(callback.from_user.id): return
    if not selected_chats:
        return await callback.answer("Сначала выберите хотя бы одну группу!", show_alert=True)
    await callback.message.edit_text("✍️ Введите текст для рассылки в группы:")
    await state.set_state(SpammerStates.waiting_for_text)

@dp.message(SpammerStates.waiting_for_text)
async def process_text(message: types.Message, state: FSMContext):
    if not is_allowed(message.from_user.id): return
    await state.update_data(spam_text=message.text)
    await message.answer("⏱ **Интервал 1:** Пауза внутри ОДНОГО чата (каждые Х секунд сообщение повторится):")
    await state.set_state(SpammerStates.waiting_for_msg_interval)

@dp.message(SpammerStates.waiting_for_msg_interval)
async def process_msg_interval(message: types.Message, state: FSMContext):
    if not is_allowed(message.from_user.id): return
    global current_spam_task, spam_task_running
    try:
        msg_int = max(int(message.text), 1)
        await state.update_data(msg_interval=msg_int)
        
        if len(selected_chats) >= 2:
            await message.answer("⏱ **Интервал 2:** Пауза (сдвиг) между переходами в разные чаты:")
            await state.set_state(SpammerStates.waiting_for_loop_interval)
        else:
            data = await state.get_data()
            await state.clear()
            await message.answer(f"🚀 Запущено для 1 чата. Интервал: {msg_int}с")
            current_spam_task = asyncio.create_task(infinite_spam(message, data['spam_text'], msg_int, 0))
            spam_task_running = True
    except:
        await message.answer("❌ Введите число.")

@dp.message(SpammerStates.waiting_for_loop_interval)
async def process_loop_interval(message: types.Message, state: FSMContext):
    if not is_allowed(message.from_user.id): return
    global current_spam_task, spam_task_running
    try:
        loop_int = max(int(message.text), 1)
        data = await state.get_data()
        await state.clear()
        
        await message.answer(f"🚀 **Рассылка по группам запущена!**\nЧастота одного чата: {data['msg_interval']}с\nСдвиг между чатами: {loop_int}с")
        current_spam_task = asyncio.create_task(infinite_spam(message, data['spam_text'], data['msg_interval'], loop_int))
        spam_task_running = True
    except:
        await message.answer("❌ Введите число.")

async def infinite_spam(message: types.Message, text: str, t1: int, t2: int):
    global spam_task_running
    client = clients[current_account]
    
    while spam_task_running:
        start_loop_time = time.time()
        
        for index, (chat_id, topic_id, name) in enumerate(selected_chats):
            if not spam_task_running: break
            
            target_send_time = start_loop_time + (index * t2)
            now = time.time()
            if target_send_time > now:
                await asyncio.sleep(target_send_time - now)
                
            try:
                if topic_id is not None:
                    await client.send_message(chat_id, text, reply_to_message_id=topic_id)
                else:
                    await client.send_message(chat_id, text)
                await message.answer(f"✅ Лесенка [{index+1}]: Отправлено в группу -> {name}")
            except FloodWait as e:
                await asyncio.sleep(e.value)
            except Exception as e:
                await message.answer(f"❌ Ошибка группы {chat_id}: {str(e)[:50]}")
                
        if not spam_task_running: break
        
        elapsed = time.time() - start_loop_time
        remaining_sleep = t1 - elapsed
        if remaining_sleep > 0:
            await asyncio.sleep(remaining_sleep)

# ====================== РАССЫЛКА В ЛС С ВЫБОРОМ РЕЖИМА ======================
@dp.callback_query(F.data == "start_pm_spam")
async def start_pm_spam(callback: types.CallbackQuery, state: FSMContext):
    if not is_allowed(callback.from_user.id): return
    if not target_users:
        return await callback.answer("Список юзеров пуст! Сначала загрузите их.", show_alert=True)
    await callback.message.edit_text("✍️ Введите текст сообщения для отправки в ЛС:")
    await state.set_state(SpammerStates.waiting_for_pm_text)

@dp.message(SpammerStates.waiting_for_pm_text)
async def process_pm_text(message: types.Message, state: FSMContext):
    if not is_allowed(message.from_user.id): return
    await state.update_data(pm_text=message.text)
    
    # Кнопки выбора типа рассылки
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔁 С повтором (беснонечно)", callback_data="pm_mode:repeat")],
        [InlineKeyboardButton(text="🛑 Без повтора (один раз)", callback_data="pm_mode:once")]
    ])
    await message.answer("⚙️ **Выберите тип рассылки пользователям:**", reply_markup=kb)

@dp.callback_query(F.data.startswith("pm_mode:"))
async def process_pm_mode(callback: types.CallbackQuery, state: FSMContext):
    if not is_allowed(callback.from_user.id): return
    mode = callback.data.split(":")[1]
    await state.update_data(pm_mode=mode)
    
    await callback.message.edit_text("⏱ Введите интервал (паузу) между отправками разным людям (в секундах):")
    await state.set_state(SpammerStates.waiting_for_pm_interval)

@dp.message(SpammerStates.waiting_for_pm_interval)
async def process_pm_interval(message: types.Message, state: FSMContext):
    if not is_allowed(message.from_user.id): return
    global current_spam_task, spam_task_running
    try:
        interval = max(int(message.text), 1)
        data = await state.get_data()
        
        if data['pm_mode'] == 'repeat':
            # Если с повтором, запоминаем первый таймер и спрашиваем паузу между кругами
            await state.update_data(pm_interval=interval)
            await message.answer("🔄 **Интервал для круга:** Введите паузу перед повторным кругом рассылки (в секундах):")
            await state.set_state(SpammerStates.waiting_for_pm_loop_interval)
        else:
            # Если без повтора, сразу запускаем задачу в один проход
            text = data['pm_text']
            await state.clear()
            await message.answer(f"🚀 **Рассылка в ЛС запущена (Без повтора)!**\nЮзеров: {len(target_users)}\nСдвиг: {interval}с")
            current_spam_task = asyncio.create_task(pm_spam_worker(message, text, interval, 0, repeat=False))
            spam_task_running = True
    except:
        await message.answer("❌ Введите корректное число.")

@dp.message(SpammerStates.waiting_for_pm_loop_interval)
async def process_pm_loop_interval(message: types.Message, state: FSMContext):
    if not is_allowed(message.from_user.id): return
    global current_spam_task, spam_task_running
    try:
        loop_interval = max(int(message.text), 1)
        data = await state.get_data()
        text = data['pm_text']
        interval = data['pm_interval']
        await state.clear()
        
        await message.answer(f"🚀 **Рассылка в ЛС запущена (С повтором)!**\nЮзеров: {len(target_users)}\nСдвиг между людьми: {interval}с\nПауза между кругами: {loop_interval}с")
        current_spam_task = asyncio.create_task(pm_spam_worker(message, text, interval, loop_interval, repeat=True))
        spam_task_running = True
    except:
        await message.answer("❌ Введите корректное число.")

async def pm_spam_worker(message: types.Message, text: str, interval: int, loop_interval: int, repeat: bool):
    global spam_task_running
    client = clients[current_account]
    
    while True:
        success, errors = 0, 0
        await message.answer("📥 Начинаю отправку сообщений по списку юзеров...")
        
        for index, u in enumerate(target_users):
            if not spam_task_running: break
            try:
                await client.send_message(u, text)
                success += 1
                await message.answer(f"📥 ЛС отправлено к: @{u}")
            except FloodWait as e:
                await message.answer(f"⏳ Флудвейт, спим {e.value} сек.")
                await asyncio.sleep(e.value)
            except (UsernameInvalid, PeerIdInvalid):
                errors += 1
                await message.answer(f"❌ Неверный юзернейм: @{u}")
            except Exception as e:
                errors += 1
                await message.answer(f"❌ Ошибка @{u}: {str(e)[:50]}")
                
            # Пауза (сдвиг) перед следующим пользователем
            if index < len(target_users) - 1 and spam_task_running:
                await asyncio.sleep(interval)
                
        if not spam_task_running: break
        
        if not repeat:
            # Режим без повтора завершается после 1 круга
            await message.answer(f"🏁 **Рассылка в ЛС успешно завершена!**\nУспешно доставлено: `{success}`\nОшибок: `{errors}`", reply_markup=main_menu())
            spam_task_running = False
            break
        else:
            # Режим с повтором уходит в сон перед новым кругом
            await message.answer(f"💤 Список окончен. Успешно: `{success}`. Пауза перед новым кругом: {loop_interval} сек.")
            await asyncio.sleep(loop_interval)

# ====================== СТОП И МЕНЮ ======================
@dp.message(Command("stop"))
@dp.callback_query(F.data == "stop_bot")
async def stop_spam_handler(event):
    global spam_task_running, current_spam_task
    spam_task_running = False
    if current_spam_task:
        current_spam_task.cancel()
        current_spam_task = None
    text = "🛑 Все процессы рассылки остановлены."
    if isinstance(event, types.CallbackQuery):
        await event.answer("Остановлено")
        await event.message.edit_text(text, reply_markup=main_menu())
    else:
        await event.answer(text, reply_markup=main_menu())

@dp.callback_query(F.data == "main_menu")
async def back_to_menu(callback: types.CallbackQuery):
    await callback.message.edit_text("Главное меню управления:", reply_markup=main_menu())

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
