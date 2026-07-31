UBN SDK — асинхронна Python-бібліотека для роботи з Ukrainian Bot Network.

Дозволяє ботам обмінюватися даними про присутність у чатах (або будь-яких просторах), керувати партнерськими грантами, публікувати схеми даних і підписуватися на вебхуки.

📦 Встановлення
bash
pip install git+https://gitlab.com/kit-kit4/ubn-sdk.git@v0.3.0

1. Реєстрація бота (CLI)
bash
ubn init
Введіть назву, тип, рівень доступу — отримаєте publicId та apiKey. Вони автоматично збережуться у .ubn/config.json та .env.

2. Публікація присутності (Python)
python
import asyncio
from ubn import AsyncUBN

async def main():
    # Токен береться з .env або передається явно
    async with AsyncUBN() as ubn:
        await ubn.publish_presence([
            {
                "chatId": "-1001234567890",  # або "shop:123", "weather:kyiv"
                "level": 2,
                "data": {"activity": 73, "eventsToday": 42}
            }
        ])

        bots = await ubn.get_presence(["-1001234567890"])
        print("Інші боти:", bots)

asyncio.run(main())

3. Інтеграція з Telegram-ботом (aiogram)
python
from aiogram import Bot, Dispatcher
from ubn import AsyncUBN

bot = Bot(token="TELEGRAM_TOKEN")
dp = Dispatcher()

# Глобальний екземпляр UBN
ubn = AsyncUBN(auto_publish=True, auto_publish_chats=[...])

@dp.message(commands=["status"])
async def status(message):
    result = await ubn.get_presence([str(message.chat.id)])
    await message.answer(f"Боти в чаті: {result}")

async def main():
    # Фонове оновлення присутності (кожні 5 хв) – автоматично
    await dp.start_polling(bot)


 Ключові концепції
chatId – універсальний ідентифікатор простору (namespace)
Це рядок, який ідентифікує контекст, де ваш бот присутній.
Може бути:

Telegram chat ID: -1001234567890

Сервісний простір: shop:123, weather:kyiv, rss:bbc, economy:main

Будь-який інший текстовий ідентифікатор.

Рівні доступу

1 – Presence	Базова активність (число 0–100).
2 – Shared Data	Додаткова статистика (наприклад, eventsToday).
3 – Custom Integration	Довільні кастомні поля (до 2KB).

 CLI (основні команди)
bash
ubn init                 # Інтерактивна реєстрація
ubn info                 # Показати свій профіль, схеми, гранти
ubn presence publish --file chats.json   # Публікація з JSON-файлу
ubn presence get chat1 chat2             # Отримати присутність
ubn grants add <public_id> <level>       # Видати грант
ubn schemas publish economy 1.0 schema.json  # Опублікувати схему
ubn discover --capability games          # Пошук ботів
Повний список: ubn --help або документація CLI.

 Конфігурація
Пріоритет (від вищого до нижчого):

Аргументи конструктора AsyncUBN(token=..., public_id=...)

Змінні середовища UBN_TOKEN, UBN_ID, UBN_BASE_URL

.env (автоматично завантажується)

Файл .ubn/config.json (створюється після ubn init)