import asyncio
import os
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

# Настройка логов
logging.basicConfig(level=logging.INFO)

# Токен берем из переменной окружения (на Render мы ее добавим)
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("Токен не найден! Добавь BOT_TOKEN в переменные окружения.")

bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- "База данных" в памяти (для сырой версии) ---
# Структура: {user_id: {"partner_id": id, "eaten": 0, "drunk": 0, "praised": 0}}
users_db = {}
# Хранилище состояний: {user_id: "waiting_for_food" | "waiting_for_water"}
user_states = {}

# --- Клавиатуры ---
def get_main_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.button(text="🍔 Я поел")
    builder.button(text="💧 Я попил")
    builder.button(text="👤 Профиль")
    builder.button(text="📢 Попросить партнера")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def get_request_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.button(text="Попросить поесть")
    builder.button(text="Попросить попить")
    builder.button(text="Назад")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def get_praise_keyboard(target_id):
    builder = InlineKeyboardBuilder()
    builder.button(text="❤️ Похвалить", callback_data=f"praise:{target_id}")
    return builder.as_markup()

# --- Хэндлеры ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    # Простая логика: если пользователь новый, просим ID партнера (для простоты сырой версии)
    # В идеале тут нужна система приглашений, но для теста сгодится и так.
    user_id = message.from_user.id
    if user_id not in users_db:
        users_db[user_id] = {"partner_id": None, "eaten": 0, "drunk": 0, "praised": 0}
        await message.answer(
            f"Привет! Твой ID: `{user_id}`.\n"
            "Чтобы связать аккаунты, попроси партнера узнать свой ID (командой /start) и отправь мне его ID командой:\n"
            "`/link ID_партнера`\n\n"
            "А пока можешь пользоваться меню:",
            reply_markup=get_main_keyboard(),
            parse_mode="Markdown"
        )
    else:
        await message.answer("С возвращением! Выбери действие:", reply_markup=get_main_keyboard())

@dp.message(Command("link"))
async def cmd_link(message: types.Message):
    try:
        partner_id = int(message.text.split()[1])
        user_id = message.from_user.id
        if user_id in users_db:
            users_db[user_id]["partner_id"] = partner_id
            # Создаем запись для партнера, если ее нет, и связываем обратно
            if partner_id not in users_db:
                users_db[partner_id] = {"partner_id": user_id, "eaten": 0, "drunk": 0, "praised": 0}
            else:
                users_db[partner_id]["partner_id"] = user_id
            await message.answer("Вы связаны! Теперь вы будете получать уведомления друг друга.")
        else:
            await message.answer("Сначала нажми /start")
    except (IndexError, ValueError):
        await message.answer("Ошибка. Используй: `/link ТВОЙ_ID_ПАРТНЕРА`", parse_mode="Markdown")

@dp.message(F.text == "🍔 Я поел")
async def ate_food(message: types.Message):
    user_states[message.from_user.id] = "waiting_for_food"
    await message.answer("Что ты съел? Напиши текстом или отправь фото 📸")

@dp.message(F.text == "💧 Я попил")
async def drank_water(message: types.Message):
    user_states[message.from_user.id] = "waiting_for_water"
    await message.answer("Что ты выпил? Напиши текстом или отправь фото 💧")

@dp.message(F.photo | F.text)
async def handle_input(message: types.Message):
    user_id = message.from_user.id
    state = user_states.get(user_id)
    
    # Если пользователь не в процессе ввода, игнорируем (или можно дать подсказку)
    if not state:
        return

    partner_id = users_db.get(user_id, {}).get("partner_id")
    content = message.text if message.text else "Фото"
    
    # Обновляем счетчики
    if state == "waiting_for_food":
        users_db[user_id]["eaten"] += 1
        action_text = "поел(а)"
    elif state == "waiting_for_water":
        users_db[user_id]["drunk"] += 1
        action_text = "попил(а)"
    else:
        return

    # Сбрасываем состояние
    del user_states[user_id]
    
    await message.answer("Записано! ✅", reply_markup=get_main_keyboard())

    # Отправляем партнеру
    if partner_id and partner_id in users_db:
        try:
            user_name = message.from_user.full_name
            if message.photo:
                await bot.send_photo(
                    chat_id=partner_id,
                    photo=message.photo[-1].file_id,
                    caption=f"❤️ {user_name} {action_text}!\n(Нажми, чтобы похвалить)",
                    reply_markup=get_praise_keyboard(user_id)
                )
            else:
                await bot.send_message(
                    chat_id=partner_id,
                    text=f"❤️ {user_name} {action_text}: {content}\n(Нажми, чтобы похвалить)",
                    reply_markup=get_praise_keyboard(user_id)
                )
        except Exception as e:
            logging.error(f"Не удалось отправить сообщение партнеру: {e}")

# Обработка кнопки "Похвалить"
@dp.callback_query(F.data.startswith("praise:"))
async def process_praise(callback: types.CallbackQuery):
    target_id = int(callback.data.split(":")[1])
    praiser_name = callback.from_user.full_name
    
    if target_id in users_db:
        users_db[target_id]["praised"] += 1
        
        # Уведомляем того, кого похвалили
        try:
            await bot.send_message(
                chat_id=target_id,
                text=f"✨ {praiser_name} похвалил(а) вас! Так держать!"
            )
        except Exception:
            pass
        
        await callback.answer("Похвала отправлена!")
        # Можно убрать кнопку или изменить текст
        await callback.message.edit_reply_markup(reply_markup=None)
    else:
        await callback.answer("Пользователь не найден.")

@dp.message(F.text == "👤 Профиль")
async def show_profile(message: types.Message):
    user_id = message.from_user.id
    data = users_db.get(user_id)
    if not data:
        await message.answer("Нажми /start для регистрации.")
        return
    
    partner_data = users_db.get(data["partner_id"], {})
    
    text = (
        f"📊 **Твой профиль**\n"
        f"🍔 Поел: {data['eaten']}\n"
        f"💧 Попил: {data['drunk']}\n"
        f"❤️ Похвал получено: {data['praised']}\n\n"
        f"👥 **Партнер**\n"
    )
    if partner_data:
        text += (
            f"🍔 Поел: {partner_data.get('eaten', 0)}\n"
            f"💧 Попил: {partner_data.get('drunk', 0)}\n"
            f"❤️ Похвал получено: {partner_data.get('praised', 0)}"
        )
    else:
        text += "Партнер еще не привязан. Используй /link"
    
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "📢 Попросить партнера")
async def ask_partner(message: types.Message):
    await message.answer("Что попросить?", reply_markup=get_request_keyboard())

@dp.message(F.text == "Попросить поесть")
async def request_food(message: types.Message):
    await send_request(message, "поесть 🍔")

@dp.message(F.text == "Попросить попить")
async def request_water(message: types.Message):
    await send_request(message, "попить 💧")

@dp.message(F.text == "Назад")
async def back_to_menu(message: types.Message):
    await message.answer("Главное меню", reply_markup=get_main_keyboard())

async def send_request(message: types.Message, what: str):
    user_id = message.from_user.id
    partner_id = users_db.get(user_id, {}).get("partner_id")
    if partner_id:
        try:
            await bot.send_message(
                chat_id=partner_id,
                text=f"🔔 Твой партнер просит тебя {what}!"
            )
            await message.answer("Запрос отправлен!", reply_markup=get_main_keyboard())
        except Exception:
            await message.answer("Не удалось отправить. Возможно, партнер не начинал диалог с ботом.", reply_markup=get_main_keyboard())
    else:
        await message.answer("Сначала привяжи партнера через /link", reply_markup=get_main_keyboard())

# --- Запуск (с веб-сервером для Render) ---
async def main():
    # Render требует, чтобы приложение слушало порт (Web Service)
    # Запускаем простой сервер, чтобы Render не ругался
    from aiohttp import web
    
    async def handle(request):
        return web.Response(text="Bot is running!")
    
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.getenv("PORT", 8080)))
    await site.start()
    
    # Запускаем бота
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
