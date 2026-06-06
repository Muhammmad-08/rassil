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

class AuthStates(StatesGroup):
    waiting_phone = State()
    waiting_code = State()

class SendStates(StatesGroup):
    waiting_chat = State()
    waiting_text = State()
    waiting_interval = State()

auth_data = {}

def main_menu_kbd():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📡 Статус сессии", callback_data="status")],
        [InlineKeyboardButton(text="🔑 Войти в аккаунт", callback_data="auth")],
        [InlineKeyboardButton(text="📨 Создать рассылку", callback_data="new_task")],
        [InlineKeyboardButton(text="📋 Активные задачи", callback_data="list_tasks")],
    ])

def is_owner(user_id: int) -> bool:
    return user_id == config.OWNER_ID

@dp.message(Command("start"))
async def start(message: types.Message, state: FSMContext):
    if not is_owner(message.from_user.id):
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
    if not is_owner(message.from_user.id):
        return
    await state.clear()
    await message.answer("🏠 Главное меню:", reply_markup=main_menu_kbd())

@dp.callback_query(F.data == "status")
async def cb_status(call: types.CallbackQuery):
    if not is_owner(call.from_user.id):
        await call.answer("⛔️", show_alert=True)
        return
    connected = await userbot.is_connected()
    jobs = scheduler.get_jobs()
    text = (
        f"📡 *Статус:* {'✅ Авторизован' if connected else '❌ Не авторизован'}\n"
        f"📋 *Активных задач:* {len(jobs)}"
    )
    await call.message.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_main")]
    ]))

@dp.callback_query(F.data == "auth")
async def cb_auth(call: types.CallbackQuery, state: FSMContext):
    if not is_owner(call.from_user.id):
        await call.answer("⛔️", show_alert=True)
        return
    await call.message.edit_text(
        f"📱 Введи номер телефона:\n\n`{config.OWNER_PHONE}`",
        parse_mode="Markdown"
    )
    await state.set_state(AuthStates.waiting_phone)

@dp.message(AuthStates.waiting_phone)
async def process_phone(message: types.Message, state: FSMContext):
    if not is_owner(message.from_user.id):
        return
    phone = message.text.strip()
    if phone != config.OWNER_PHONE:
        await message.answer("❌ Неверный номер. Введи свой номер или /menu")
        return
    await message.answer("⏳ Отправляю код...")
    try:
        phone_code_hash = await userbot.send_code(phone)
        auth_data[message.from_user.id] = {"phone": phone, "phone_code_hash": phone_code_hash}
        await message.answer(
            "🔑 Код отправлен!\n\n"
            "⚡️ *Введи его СРАЗУ* (действует ~2 минуты):",
            parse_mode="Markdown"
        )
        await state.set_state(AuthStates.waiting_code)
    except Exception as e:
        await message.answer(f"❌ Ошибка: `{e}`", parse_mode="Markdown")
        await state.clear()

@dp.message(AuthStates.waiting_code)
async def process_code(message: types.Message, state: FSMContext):
    if not is_owner(message.from_user.id):
        return
    code = message.text.strip().replace(" ", "")
    data = auth_data.get(message.from_user.id)
    if not data:
        await message.answer("❌ Сессия истекла. /menu")
        await state.clear()
        return
    try:
        session_string = await userbot.sign_in(data["phone"], data["phone_code_hash"], code)
        auth_data.pop(message.from_user.id, None)
        await state.clear()
        await message.answer(
            "✅ *Успешно авторизован!*\n\n"
            "⚠️ Чтобы сессия не сбрасывалась при перезапуске Railway, "
            "добавь переменную:\n\n"
            "`SESSION_STRING` =\n"
            f"`{session_string}`\n\n"
            "Скопируй строку выше и вставь в Railway Variables.",
            parse_mode="Markdown",
            reply_markup=main_menu_kbd()
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: `{e}`\n\nПопробуй /menu", parse_mode="Markdown")
        await state.clear()

@dp.callback_query(F.data == "new_task")
async def cb_new_task(call: types.CallbackQuery, state: FSMContext):
    if not is_owner(call.from_user.id):
        await call.answer("⛔️", show_alert=True)
        return
    connected = await userbot.is_connected()
    if not connected:
        await call.message.edit_text(
            "❌ Сначала войди в аккаунт!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="back_main")]
            ])
        )
        return
    await call.message.edit_text(
        "📨 *Новая задача*\n\nШаг 1/3: Username или ID чата\nПример: `@mychat`",
        parse_mode="Markdown"
    )
    await state.set_state(SendStates.waiting_chat)

@dp.message(SendStates.waiting_chat)
async def process_chat(message: types.Message, state: FSMContext):
    if not is_owner(message.from_user.id):
        return
    await state.update_data(chat=message.text.strip())
    await message.answer("✏️ Шаг 2/3: Введи текст сообщения:")
    await state.set_state(SendStates.waiting_text)

@dp.message(SendStates.waiting_text)
async def process_text(message: types.Message, state: FSMContext):
    if not is_owner(message.from_user.id):
        return
    await state.update_data(text=message.text)
    await message.answer("⏱ Шаг 3/3: Интервал в *минутах* (например `30`):", parse_mode="Markdown")
    await state.set_state(SendStates.waiting_interval)

@dp.message(SendStates.waiting_interval)
async def process_interval(message: types.Message, state: FSMContext):
    if not is_owner(message.from_user.id):
        return
    try:
        interval = int(message.text.strip())
        if interval < 1:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи число, например: `30`", parse_mode="Markdown")
        return
    data = await state.get_data()
    job_id = str(uuid.uuid4())[:8]
    scheduler.add_job(job_id, data["chat"], data["text"], interval)
    await state.clear()
    await message.answer(
        f"✅ *Задача создана!*\n\n"
        f"🆔 `{job_id}`\n💬 `{data['chat']}`\n⏱ каждые {interval} мин.",
        parse_mode="Markdown",
        reply_markup=main_menu_kbd()
    )

@dp.callback_query(F.data == "list_tasks")
async def cb_list_tasks(call: types.CallbackQuery):
    if not is_owner(call.from_user.id):
        await call.answer("⛔️", show_alert=True)
        return
    jobs = scheduler.get_jobs()
    if not jobs:
        await call.message.edit_text("📋 Задач нет.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_main")]
        ]))
        return
    buttons = []
    text = "📋 *Активные задачи:*\n\n"
    for job_id, info in jobs.items():
        text += f"🆔 `{job_id}` | `{info['chat']}` | каждые {info['interval']} мин.\n📝 {info['text'][:40]}\n\n"
        buttons.append([InlineKeyboardButton(text=f"🗑 Удалить {job_id}", callback_data=f"del_{job_id}")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_main")])
    await call.message.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("del_"))
async def cb_delete_task(call: types.CallbackQuery):
    if not is_owner(call.from_user.id):
        await call.answer("⛔️", show_alert=True)
        return
    job_id = call.data.replace("del_", "")
    scheduler.remove_job(job_id)
    await call.answer(f"✅ Удалено")
    await cb_list_tasks(call)

@dp.callback_query(F.data == "back_main")
async def cb_back_main(call: types.CallbackQuery, state: FSMContext):
    if not is_owner(call.from_user.id):
        return
    await state.clear()
    await call.message.edit_text("🏠 Главное меню:", reply_markup=main_menu_kbd())

async def main():
    scheduler.start()
    await userbot.init()  # восстанавливаем сессию если есть SESSION_STRING
    print("✅ Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
