from pyrogram import Client
import config
import os

# Клиент юзербота — singleton
_userbot: Client = None

def get_userbot() -> Client:
    global _userbot
    if _userbot is None:
        _userbot = Client(
            name="user_session",
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            workdir="/tmp"
        )
    return _userbot

async def is_connected() -> bool:
    try:
        ub = get_userbot()
        return ub.is_connected
    except:
        return False

async def send_code(phone: str):
    ub = get_userbot()
    if not ub.is_connected:
        await ub.connect()
    sent = await ub.send_code(phone)
    return sent.phone_code_hash

async def sign_in(phone: str, phone_code_hash: str, code: str):
    ub = get_userbot()
    await ub.sign_in(phone, phone_code_hash, code)

async def send_message_as_user(chat: str, text: str):
    ub = get_userbot()
    if not ub.is_connected:
        await ub.connect()
    await ub.send_message(chat, text)
