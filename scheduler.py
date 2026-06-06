from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
import userbot

scheduler = AsyncIOScheduler(timezone="UTC")
# Хранилище задач: { job_id: {chat, text, interval_minutes} }
active_jobs: dict = {}

def get_jobs() -> dict:
    return active_jobs

async def _send_job(chat: str, text: str):
    try:
        await userbot.send_message_as_user(chat, text)
        print(f"[Scheduler] Отправлено в {chat}: {text[:30]}...")
    except Exception as e:
        print(f"[Scheduler] Ошибка: {e}")

def add_job(job_id: str, chat: str, text: str, interval_minutes: int):
    scheduler.add_job(
        _send_job,
        trigger=IntervalTrigger(minutes=interval_minutes),
        args=[chat, text],
        id=job_id,
        replace_existing=True
    )
    active_jobs[job_id] = {
        "chat": chat,
        "text": text,
        "interval": interval_minutes
    }

def remove_job(job_id: str):
    try:
        scheduler.remove_job(job_id)
    except:
        pass
    active_jobs.pop(job_id, None)

def start():
    if not scheduler.running:
        scheduler.start()
