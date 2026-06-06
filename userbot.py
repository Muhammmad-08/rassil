from pyrogram import Client
from pyrogram.errors import SessionPasswordNeeded
import config
import os
import asyncio

_client: Client = None
_authorized: bool = False

def _make_client():
    # Если есть сохранённая session string — используем её
    session_string = os.getenv("SESSION_STRING", "")
    if session_string:
        return Client(
            name="user_session",
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            session_string=session_string
        )
    return Client(
        name="user_session",
        api_id=config.API_ID,
        api_hash=config.API_HASH,
        workdir="/tmp",
        in_memory=True
    )

async def init():
    """Вызывается при старте — если есть SESSION_STRING, авторизуемся автоматически"""
    global _client, _authorized
    session_string = os.getenv("SESSION_STRING", "")
    if session_string:
        try:
            _client = _make_client()
            await _client.start()
            _authorized = True
            me = await _client.get_me()
            print(f"✅ Юзербот авторизован как {me.first_name} (@{me.username})")
        except Exception as e:
            print(f"⚠️ Не удалось восстановить сессию: {e}")
            _authorized = False

async def send_code(phone: str) -> str:
    global _client, _authorized
    _authorized = False
    _client = Client(
        name="user_session",
        api_id=config.API_ID,
        api_hash=config.API_HASH,
        workdir="/tmp",
        in_memory=True
    )
    await _client.connect()
    sent = await _client.send_code(phone)
    return sent.phone_code_hash

async def sign_in(phone: str, phone_code_hash: str, code: str) -> str:
    """Возвращает session_string для сохранения в Railway Variables"""
    global _client, _authorized
    if _client is None:
        raise Exception("Сначала запроси код")

    try:
        await _client.sign_in(phone, phone_code_hash, code)
    except SessionPasswordNeeded:
        raise Exception("Аккаунт защищён паролем 2FA — не поддерживается.")

    _authorized = True
    # Экспортируем строку сессии
    session_string = await _client.export_session_string()
    return session_string

async def is_connected() -> bool:
    global _client, _authorized
    if not _authorized or _client is None:
        return False
    try:
        me = await _client.get_me()
        return me is not None
    except:
        return False

async def send_message_as_user(chat: str, text: str):
    global _client, _authorized
    if not _authorized or _client is None:
        raise Exception("Юзербот не авторизован")
    await _client.send_message(chat, text)
