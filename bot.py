import asyncio
import os
import logging
import secrets
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN not set")

bot = Bot(token=TOKEN)
dp = Dispatcher()

users_db = {}
user_states = {}
invites = {}

def new_user():
    return {"partner_id": None, "eaten": 0, "drunk": 0, "praised": 0, "paired": False}

def ensure_user(uid):
    if uid not in users_db:
        users_db[uid] = new_user()

def get_main_keyboard():
    b = ReplyKeyboardBuilder()
    b.button(text="🍔 Я поел")
    b.button(text="💧 Я попил")
    b.button(text="👤 Профиль")
    b.button(text="📊 Статистика пары")
    b.button(text="📢 Попросить партнера")
    b.button(text="🔗 Пригласить партнера")
    b.adjust(2, 2, 2)
    return b.as_markup(resize_keyboard=True)

def get_request_keyboard():
    b = ReplyKeyboardBuilder()
    b.button(text="Попросить поесть")
    b.button(text="Попросить попить")
    b.button(text="Назад")
    b.adjust(2, 1)
    return b.as_markup(resize_keyboard=True)

def get_praise_keyboard(target_id):
    b = InlineKeyboardBuilder()
    b.button(text="❤️ Похвалить", callback_data=f"praise:{target_id}")
    return b.as_markup()

def get_invite_keyboard(link):
    b = InlineKeyboardBuilder()
    b.button(text="📤 Поделиться ссылкой", url=f"https://t.me/share/url?url={link}&text=Присоединяйся ко мне в боте!")
    return b.as_markup()

@dp.message(CommandStart())
async def cmd_start(message: types.Message, command: CommandStart = None):
    uid = message.from_user.id
    ensure_user(uid)

    if users_db[uid]["paired"]:
        await message.answer("С возвращением! Выбери действие:", reply_markup=get_main_keyboard())
        return

    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        code = args[1].strip()
        if code in invites:
            inviter_id = invites.pop(code)

            if inviter_id == uid:
                await message.answer("Нельзя связать себя с собой 😅", reply_markup=get_main_keyboard())
                return

            if inviter_id not in users_db:
                await message.answer("Приглашение недействительно — пользователь не найден.", reply_markup=get_main_keyboard())
                return

            if users_db[inviter_id]["paired"] or users_db[uid]["paired"]:
                await message.answer("Один из вас уже состоит в паре. Сначала нужно разорвать текущую связь.", reply_markup=get_main_keyboard())
                return

            users_db[uid]["partner_id"] = inviter_id
            users_db[uid]["paired"] = True
            users_db[inviter_id]["partner_id"] = uid
            users_db[inviter_id]["paired"] = True

            partner_name = message.from_user.full_name
            try:
                await bot.send_message(
                    inviter_id,
                    f"🎉 {partner_name} присоединился(ась) к тебе по ссылке! Теперь вы пара."
                )
            except Exception:
                pass

            await message.answer("🎉 Вы успешно связаны! Теперь вы пара.", reply_markup=get_main_keyboard())
            return

        await message.answer("Ссылка недействительна или устарела.", reply_markup=get_main_keyboard())
        return

    await message.answer(
        f"Привет, {message.from_user.full_name}!\n\n"
        "Нажми «🔗 Пригласить партнера», чтобы получить ссылку и начать вести учёт вместе.",
        reply_markup=get_main_keyboard()
    )

@dp.message(F.text == "🔗 Пригласить партнера")
async def invite_partner(message: types.Message):
    uid = message.from_user.id
    ensure_user(uid)

    if users_db[uid]["paired"]:
        await message.answer("Ты уже в паре. Сначала нужно разорвать текущую связь.")
        return

    code = secrets.token_urlsafe(8)
    invites[code] = uid

    bot_username = (await bot.get_me()).username
    link = f"https://t.me/{bot_username}?start={code}"

    await message.answer(
        "Отправь эту ссылку партнёру:\n\n"
        f"{link}\n\n"
        "Ссылка одноразовая.",
        reply_markup=get_invite_keyboard(link)
    )

@dp.message(F.text == "🍔 Я поел")
async def ate_food(message: types.Message):
    ensure_user(message.from_user.id)
    user_states[message.from_user.id] = "waiting_for_food"
    await message.answer("Что ты съел? Напиши текстом или отправь фото 📸")

@dp.message(F.text == "💧 Я попил")
async def drank_water(message: types.Message):
    ensure_user(message.from_user.id)
    user_states[message.from_user.id] = "waiting_for_water"
    await message.answer("Что ты выпил? Напиши текстом или отправь фото 💧")

@dp.message(F.photo | F.text)
async def handle_input(message: types.Message):
    uid = message.from_user.id
    state = user_states.get(uid)
    if not state:
        return

    if not users_db.get(uid, {}).get("paired"):
        del user_states[uid]
        await message.answer("Сначала пригласи партнёра по ссылке (🔗 Пригласить партнера).", reply_markup=get_main_keyboard())
        return

    partner_id = users_db[uid]["partner_id"]
    content = message.text if message.text else "Фото"

    if state == "waiting_for_food":
        users_db[uid]["eaten"] += 1
        action_text = "поел(а)"
    else:
        users_db[uid]["drunk"] += 1
        action_text = "попил(а)"

    del user_states[uid]
    await message.answer("Записано ✅", reply_markup=get_main_keyboard())

    if partner_id and partner_id in users_db:
        try:
            user_name = message.from_user.full_name
            if message.photo:
                await bot.send_photo(
                    chat_id=partner_id,
                    photo=message.photo[-1].file_id,
                    caption=f"❤️ {user_name} {action_text}!",
                    reply_markup=get_praise_keyboard(uid)
                )
            else:
                await bot.send_message(
                    chat_id=partner_id,
                    text=f"❤️ {user_name} {action_text}: {content}",
                    reply_markup=get_praise_keyboard(uid)
                )
        except Exception as e:
            logging.error(f"Не удалось отправить сообщение партнёру: {e}")

@dp.callback_query(F.data.startswith("praise:"))
async def process_praise(callback: types.CallbackQuery):
    target_id = int(callback.data.split(":")[1])
    praiser_name = callback.from_user.full_name

    if target_id in users_db:
        users_db[target_id]["praised"] += 1
        try:
            await bot.send_message(target_id, f"✨ {praiser_name} похвалил(а) тебя! Так держать!")
        except Exception:
            pass
        await callback.answer("Похвала отправлена!")
        await callback.message.edit_reply_markup(reply_markup=None)
    else:
        await callback.answer("Пользователь не найден.")

@dp.message(F.text == "👤 Профиль")
async def show_profile(message: types.Message):
    uid = message.from_user.id
    ensure_user(uid)
    data = users_db[uid]

    if not data["paired"]:
        await message.answer("Ты пока не в паре. Нажми «🔗 Пригласить партнера».", reply_markup=get_main_keyboard())
        return

    pdata = users_db.get(data["partner_id"], new_user())

    text = (
        f"📊 *Твой профиль*\n"
        f"🍔 Поел: {data['eaten']}\n"
        f"💧 Попил: {data['drunk']}\n"
        f"❤️ Похвал получено: {data['praised']}\n\n"
        f"👥 *Партнёр*\n"
        f"🍔 Поел: {pdata['eaten']}\n"
        f"💧 Попил: {pdata['drunk']}\n"
        f"❤️ Похвал получено: {pdata['praised']}"
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=get_main_keyboard())

@dp.message(F.text == "📊 Статистика пары")
async def couple_stats(message: types.Message):
    uid = message.from_user.id
    ensure_user(uid)
    data = users_db[uid]

    if not data["paired"]:
        await message.answer("Статистика доступна только в паре.", reply_markup=get_main_keyboard())
        return

    pdata = users_db.get(data["partner_id"], new_user())

    total_eaten = data["eaten"] + pdata["eaten"]
    total_drunk = data["drunk"] + pdata["drunk"]
    total_praise = data["praised"] + pdata["praised"]

    text = (
        f"📈 *Статистика пары*\n\n"
        f"🍔 Всего поели: {total_eaten}\n"
        f"💧 Всего попили: {total_drunk}\n"
        f"❤️ Всего похвал: {total_praise}\n\n"
        f"_Вы вместе следите за едой и водой!_"
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=get_main_keyboard())

@dp.message(F.text == "📢 Попросить партнера")
async def ask_partner(message: types.Message):
    if not users_db.get(message.from_user.id, {}).get("paired"):
        await message.answer("Сначала пригласи партнёра.", reply_markup=get_main_keyboard())
        return
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
    uid = message.from_user.id
    ensure_user(uid)
    partner_id = users_db[uid].get("partner_id")
    if not users_db[uid].get("paired") or not partner_id:
        await message.answer("Сначала пригласи партнёра.", reply_markup=get_main_keyboard())
        return
    try:
        await bot.send_message(partner_id, f"🔔 Твой партнёр просит тебя {what}!")
        await message.answer("Запрос отправлен!", reply_markup=get_main_keyboard())
    except Exception:
        await message.answer("Не удалось отправить. Возможно, партнёр не начинал диалог с ботом.", reply_markup=get_main_keyboard())

async def main():
    from aiohttp import web

    async def handle(request):
        return web.Response(text="Bot is running!")

    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 8080)))
    await site.start()

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
