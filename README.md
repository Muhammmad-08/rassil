# 🤖 Telegram Controller Bot

Простой управляющий Telegram бот на Pyrogram.

## Команды

| Команда | Описание |
|---|---|
| `/start` | Приветствие |
| `/send @username текст` | Отправить сообщение пользователю |
| `/me` | Информация о боте |
| `/help` | Список команд |

## Деплой на Railway

### 1. Загрузи на GitHub
```bash
git init
git add .
git commit -m "init"
git branch -M main
git remote add origin https://github.com/ТВО_ЮЮ/НАЗВАНИЕ.git
git push -u origin main
```

### 2. Railway
1. Зайди на [railway.app](https://railway.app)
2. **New Project → Deploy from GitHub repo**
3. Выбери репозиторий
4. Перейди в **Variables** и добавь:

| Переменная | Значение |
|---|---|
| `API_ID` | твой api_id |
| `API_HASH` | твой api_hash |
| `BOT_TOKEN` | токен от BotFather |

5. Railway сам задеплоит бота.

## Переменные окружения

Все секреты хранятся в переменных Railway — не в коде.
