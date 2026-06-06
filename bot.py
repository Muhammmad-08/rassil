import asyncio
import uuid
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

import config
import userbot
import scheduler

bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher()

# ===================== FSM =====================

class AuthStates(StatesGroup):
    waiting_phone = State()
    waiting_code = State()

class SendStates(StatesGroup):
    waiting_chat = State()
    waiting_text = State()
    waiting_interval = State()

# ===================== AUTH DATA =====================
auth_data = {}

# ===================== ГЛАВНОЕ МЕНЮ =====================

def main_menu_kbd():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📡 Статус сессии", callback_data="status")],
        [InlineKeyboardButton(text="🔑 Войти в аккаунт", callback_data="auth")],
        [InlineKeyboardButton(text="📨 Создать рассылку", callback_data="new_task")],
        [InlineKeyboardButton(text="📋 Активные задачи", callback_data="list_tasks")],
    ])

# ===================== КОМАНДЫ =====================

@dp.message(Command("start"))
async def start(message: types.Message, state: FSMContext):
    if message.from_user.id != config.OWNER_ID:
        await message.answer("⛔️ Нет доступа.")
        return
    await state.clear()
    await message.answer(
        "👋 *Панель управления юзерботом*\n\nВыбери действие:",
        parse_mode="Markdown",
        reply_markup=main_menu_kbd()
    )

@dp.message(Command("menu"))
async def menu_cmd(message: types.Message, state: FSMContext):
    if message.from_user.id != config.OWNER_ID:
        return
    await state.clear()
    await message.answer("🏠 Главное меню:", reply_markup=main_menu_kbd())

# ===================== СТАТУС =====================

@dp.callback_query(F.data == "status")
async def cb_status(call: types.CallbackQuery):
    if call.from_user.id != config.OWNER_ID:
        await call.answer("⛔️ Нет доступа", show_alert=True)
        return
    connected = await userbot.is_connected()
    jobs = scheduler.get_jobs()
    text = (
        f"📡 *Статус сессии:* {'✅ Активна' if connected else '❌ Не авторизован'}\n"
        f"📋 *Активных задач:* {len(jobs)}"
    )
    kbd = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_main")]
    ])
    await call.message.edit_text(text, parse_mode="Markdown", reply_markup=kbd)

# ===================== АВТОРИЗАЦИЯ =====================

@dp.callback_query(F.data == "auth")
async def cb_auth(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id != config.OWNER_ID:
        await call.answer("⛔️ Нет доступа", show_alert=True)
        return
    await call.message.edit_text(
        f"📱 Введи свой номер телефона.\n\n"
        f"Только номер `{config.OWNER_PHONE}` будет принят.\n\n"
        f"Формат: `+2348103231706`",
        parse_mode="Markdown"
    )
    await state.set_state(AuthStates.waiting_phone)

@dp.message(AuthStates.waiting_phone)
async def process_phone(message: types.Message, state: FSMContext):
    if message.from_user.id != config.OWNER_ID:
        return
    phone = message.text.strip()
    if phone != config.OWNER_PHONE:
        await message.answer(
            "❌ Номер не совпадает с номером владельца.\n"
            "Введи правильный номер или /menu для отмены."
        )
        return
    await message.answer("⏳ Отправляю код в Telegram...")
    try:
        phone_code_hash = await userbot.send_code(phone)
        auth_data[message.from_user.id] = {
            "phone": phone,
            "phone_code_hash": phone_code_hash
        }
        await message.answer(
            "🔑 Код отправлен в Telegram!\n\n"
            "Введи его сюда (только цифры, например: `12345`):",
            parse_mode="Markdown"
        )
        await state.set_state(AuthStates.waiting_code)
    except Exception as e:
        await message.answer(f"❌ Ошибка: `{e}`\n\nПопробуй снова /menu", parse_mode="Markdown")
        await state.clear()

@dp.message(AuthStates.waiting_code)
async def process_code(message: types.Message, state: FSMContext):
    if message.from_user.id != config.OWNER_ID:
        return
    code = message.text.strip().replace(" ", "").replace("_", "")
    data = auth_data.get(message.from_user.id)
    if not data:
        await message.answer("❌ Сессия истекла. Начни заново /menu")
        await state.clear()
        return
    try:
        await userbot.sign_in(data["phone"], data["phone_code_hash"], code)
        auth_data.pop(message.from_user.id, None)
        await state.clear()
        await message.answer(
            "✅ *Успешно авторизован!*\n\n"
            "Теперь бот будет отправлять сообщения от твоего имени.",
            parse_mode="Markdown",
            reply_markup=main_menu_kbd()
        )
    except Exception as e:
        await message.answer(f"❌ Неверный код или ошибка: `{e}`\n\nПопробуй снова /menu", parse_mode="Markdown")
        await state.clear()

# ===================== СОЗДАТЬ ЗАДАЧУ =====================

@dp.callback_query(F.data == "new_task")
async def cb_new_task(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id != config.OWNER_ID:
        await call.answer("⛔️ Нет доступа", show_alert=True)
        return
    connected = await userbot.is_connected()
    if not connected:
        await call.message.edit_text(
            "❌ Сначала войди в аккаунт!\n\nНажми 'Войти в аккаунт' в меню.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="back_main")]
            ])
        )
        return
    await call.message.edit_text(
        "📨 *Новая задача рассылки*\n\n"
        "Шаг 1/3: Введи username чата или его ID\n"
        "Например: `@mychat` или `-1001234567890`",
        parse_mode="Markdown"
    )
    await state.set_state(SendStates.waiting_chat)

@dp.message(SendStates.waiting_chat)
async def process_chat(message: types.Message, state: FSMContext):
    if message.from_user.id != config.OWNER_ID:
        return
    await state.update_data(chat=message.text.strip())
    await message.answer("✏️ Шаг 2/3: Введи текст сообщения:")
    await state.set_state(SendStates.waiting_text)

@dp.message(SendStates.waiting_text)
async def process_text(message: types.Message, state: FSMContext):
    if message.from_user.id != config.OWNER_ID:
        return
    await state.update_data(text=message.text)
    await message.answer(
        "⏱ Шаг 3/3: Введи интервал в *минутах*\n\nНапример: `30`",
        parse_mode="Markdown"
    )
    await state.set_state(SendStates.waiting_interval)

@dp.message(SendStates.waiting_interval)
async def process_interval(message: types.Message, state: FSMContext):
    if message.from_user.id != config.OWNER_ID:
        return
    try:
        interval = int(message.text.strip())
        if interval < 1:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи число минут, например: `30`", parse_mode="Markdown")
        return
    data = await state.get_data()
    chat = data["chat"]
    text = data["text"]
    job_id = str(uuid.uuid4())[:8]
    scheduler.add_job(job_id, chat, text, interval)
    await state.clear()
    await message.answer(
        f"✅ *Задача создана!*\n\n"
        f"🆔 ID: `{job_id}`\n"
        f"💬 Чат: `{chat}`\n"
        f"⏱ Каждые {interval} мин.\n"
        f"📝 {text[:50]}{'...' if len(text) > 50 else ''}",
        parse_mode="Markdown",
        reply_markup=main_menu_kbd()
    )

# ===================== СПИСОК ЗАДАЧ =====================

@dp.callback_query(F.data == "list_tasks")
async def cb_list_tasks(call: types.CallbackQuery):
    if call.from_user.id != config.OWNER_ID:
        await call.answer("⛔️ Нет доступа", show_alert=True)
        return
    jobs = scheduler.get_jobs()
    if not jobs:
        await call.message.edit_text(
            "📋 Активных задач нет.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="back_main")]
            ])
        )
        return
    buttons = []
    text = "📋 *Активные задачи:*\n\n"
    for job_id, info in jobs.items():
        text += (
            f"🆔 `{job_id}`\n"
            f"💬 `{info['chat']}`\n"
            f"⏱ каждые {info['interval']} мин.\n"
            f"📝 {info['text'][:40]}{'...' if len(info['text']) > 40 else ''}\n\n"
        )
        buttons.append([
            InlineKeyboardButton(text=f"🗑 Удалить {job_id}", callback_data=f"del_{job_id}")
        ])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_main")])
    await call.message.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("del_"))
async def cb_delete_task(call: types.CallbackQuery):
    if call.from_user.id != config.OWNER_ID:
        await call.answer("⛔️ Нет доступа", show_alert=True)
        return
    job_id = call.data.replace("del_", "")
    scheduler.remove_job(job_id)
    await call.answer(f"✅ Задача {job_id} удалена")
    await cb_list_tasks(call)

# ===================== НАЗАД =====================

@dp.callback_query(F.data == "back_main")
async def cb_back_main(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id != config.OWNER_ID:
        return
    await state.clear()
    await call.message.edit_text("🏠 Главное меню:", reply_markup=main_menu_kbd())

# ===================== ЗАПУСК =====================

async def main():
    scheduler.start()
    print("✅ Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
