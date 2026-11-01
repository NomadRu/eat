import asyncio
import os
import logging
import secrets
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

import db

logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN not set")

bot = Bot(token=TOKEN)
dp = Dispatcher()

class InputStates(StatesGroup):
    waiting_for_food = State()
    waiting_for_water = State()

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

def get_stats_keyboard():
    b = InlineKeyboardBuilder()
    b.button(text="💔 Разорвать пару", callback_data="break_pair")
    return b.as_markup()

def get_cancel_keyboard():
    b = ReplyKeyboardBuilder()
    b.button(text="Отмена")
    return b.as_markup(resize_keyboard=True)

# --- ХЭНДЛЕРЫ, КОТОРЫЕ ЛОВЯТ И КНОПКИ, И ТЕКСТ ---

@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    await db.ensure_user(uid)
    user = await db.get_user(uid)

    if user["paired"]:
        await message.answer("С возвращением! Выбери действие:", reply_markup=get_main_keyboard())
        return

    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        code = args[1].strip()
        inviter_id = await db.pop_invite(code)

        if not inviter_id:
            await message.answer("Ссылка недействительна или устарела.", reply_markup=get_main_keyboard())
            return

        if inviter_id == uid:
            await message.answer("Нельзя связать себя с собой 😅", reply_markup=get_main_keyboard())
            return

        inviter = await db.get_user(inviter_id)
        if not inviter:
            await message.answer("Приглашение недействительно.", reply_markup=get_main_keyboard())
            return

        if inviter["paired"] or user["paired"]:
            await message.answer("Один из вас уже состоит в паре.", reply_markup=get_main_keyboard())
            return

        await db.set_partner(uid, inviter_id)
        try:
            await bot.send_message(inviter_id, f"🎉 {message.from_user.full_name} присоединился(ась) к тебе по ссылке! Теперь вы пара.")
        except Exception:
            pass
        await message.answer("🎉 Вы успешно связаны! Теперь вы пара.", reply_markup=get_main_keyboard())
        return

    await message.answer("Привет! Нажми «🔗 Пригласить партнера» или напиши 'пригласить'.", reply_markup=get_main_keyboard())

# Ловим "Профиль" (кнопка или текст)
@dp.message((F.text == "👤 Профиль") | (F.text.lower() == "профиль"))
async def show_profile(message: types.Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    try:
        data = await db.ensure_user(uid)
        if not data["paired"]:
            await message.answer("Ты пока не в паре.", reply_markup=get_main_keyboard())
            return

        pdata = await db.get_user(data["partner_id"]) or {"eaten": 0, "drunk": 0, "praised": 0}
        text = (
            f"📊 *Твой профиль*\n"
            f"🍔 Поел: {data['eaten']}\n"
            f"💧 Попил: {data['drunk']}\n"
            f"❤️ Похвал: {data['praised']}\n\n"
            f"👥 *Партнёр*\n"
            f"🍔 Поел: {pdata['eaten']}\n"
            f"💧 Попил: {pdata['drunk']}\n"
            f"❤️ Похвал: {pdata['praised']}"
        )
        await message.answer(text, parse_mode="Markdown", reply_markup=get_main_keyboard())
    except Exception as e:
        await message.answer(f"Ошибка БД: {e}", reply_markup=get_main_keyboard())

# Ловим "Статистика" (кнопка или текст)
@dp.message((F.text == "📊 Статистика пары") | (F.text.lower() == "статистика"))
async def couple_stats(message: types.Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    try:
        data = await db.ensure_user(uid)
        if not data["paired"]:
            await message.answer("Статистика доступна только в паре.", reply_markup=get_main_keyboard())
            return

        pdata = await db.get_user(data["partner_id"]) or {"eaten": 0, "drunk": 0, "praised": 0}
        text = (
            f"📈 *Статистика пары*\n\n"
            f"🍔 Всего поели: {data['eaten'] + pdata['eaten']}\n"
            f"💧 Всего попили: {data['drunk'] + pdata['drunk']}\n"
            f"❤️ Всего похвал: {data['praised'] + pdata['praised']}\n\n"
            f"_Вы вместе!_"
        )
        await message.answer(text, parse_mode="Markdown", reply_markup=get_stats_keyboard())
    except Exception as e:
        await message.answer(f"Ошибка БД: {e}", reply_markup=get_main_keyboard())

# Ловим "Пригласить" (кнопка или текст)
@dp.message((F.text == "🔗 Пригласить партнера") | (F.text.lower() == "пригласить"))
async def invite_partner(message: types.Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    user = await db.ensure_user(uid)
    if user["paired"]:
        await message.answer("Ты уже в паре.", reply_markup=get_main_keyboard())
        return

    code = secrets.token_urlsafe(8)
    await db.create_invite(code, uid)
    bot_username = (await bot.get_me()).username
    link = f"https://t.me/{bot_username}?start={code}"
    await message.answer(f"Отправь ссылку партнёру:\n\n{link}", reply_markup=get_invite_keyboard(link))

# Ловим "Попросить" (кнопка или текст)
@dp.message((F.text == "📢 Попросить партнера") | (F.text.lower() == "попросить"))
async def ask_partner(message: types.Message, state: FSMContext):
    await state.clear()
    data = await db.ensure_user(message.from_user.id)
    if not data["paired"]:
        await message.answer("Сначала пригласи партнёра.", reply_markup=get_main_keyboard())
        return
    await message.answer("Что попросить?", reply_markup=get_request_keyboard())

# Запросы
@dp.message((F.text == "Попросить поесть") | (F.text.lower() == "поесть"))
async def request_food(message: types.Message, state: FSMContext):
    await state.clear()
    await send_request(message, "поесть 🍔")

@dp.message((F.text == "Попросить попить") | (F.text.lower() == "попить"))
async def request_water(message: types.Message, state: FSMContext):
    await state.clear()
    await send_request(message, "попить 💧")

# Кнопка назад
@dp.message((F.text == "Назад") | (F.text.lower() == "назад"))
async def back_to_menu(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Главное меню", reply_markup=get_main_keyboard())

# Еда (кнопка или текст)
@dp.message((F.text == "🍔 Я поел") | (F.text.lower() == "поел"))
async def ate_food(message: types.Message, state: FSMContext):
    await state.clear()
    await db.ensure_user(message.from_user.id)
    await state.set_state(InputStates.waiting_for_food)
    await message.answer("Что ты съел? Напиши или отправь фото 📸", reply_markup=get_cancel_keyboard())

# Вода (кнопка или текст)
@dp.message((F.text == "💧 Я попил") | (F.text.lower() == "попил"))
async def drank_water(message: types.Message, state: FSMContext):
    await state.clear()
    await db.ensure_user(message.from_user.id)
    await state.set_state(InputStates.waiting_for_water)
    await message.answer("Что ты выпил? Напиши или отправь фото 💧", reply_markup=get_cancel_keyboard())

@dp.message((F.text == "Отмена") | (F.text.lower() == "отмена"))
async def cancel_input(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.", reply_markup=get_main_keyboard())

# Ввод еды/воды
@dp.message(InputStates.waiting_for_food, F.photo | F.text)
async def handle_food_input(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    await state.clear()
    user = await db.get_user(uid)
    if not user or not user["paired"]:
        await message.answer("Сначала пригласи партнёра.", reply_markup=get_main_keyboard())
        return

    content = message.text if message.text else "Фото"
    await db.increment(uid, "eaten")
    await message.answer("Записано ✅", reply_markup=get_main_keyboard())
    try:
        if message.photo:
            await bot.send_photo(chat_id=user["partner_id"], photo=message.photo[-1].file_id, caption=f"❤️ {message.from_user.full_name} поел(а)!", reply_markup=get_praise_keyboard(uid))
        else:
            await bot.send_message(chat_id=user["partner_id"], text=f"❤️ {message.from_user.full_name} поел(а): {content}", reply_markup=get_praise_keyboard(uid))
    except Exception:
        pass

@dp.message(InputStates.waiting_for_water, F.photo | F.text)
async def handle_water_input(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    await state.clear()
    user = await db.get_user(uid)
    if not user or not user["paired"]:
        await message.answer("Сначала пригласи партнёра.", reply_markup=get_main_keyboard())
        return

    content = message.text if message.text else "Фото"
    await db.increment(uid, "drunk")
    await message.answer("Записано ✅", reply_markup=get_main_keyboard())
    try:
        if message.photo:
            await bot.send_photo(chat_id=user["partner_id"], photo=message.photo[-1].file_id, caption=f"❤️ {message.from_user.full_name} попил(а)!", reply_markup=get_praise_keyboard(uid))
        else:
            await bot.send_message(chat_id=user["partner_id"], text=f"❤️ {message.from_user.full_name} попил(а): {content}", reply_markup=get_praise_keyboard(uid))
    except Exception:
        pass

@dp.callback_query(F.data.startswith("praise:"))
async def process_praise(callback: types.CallbackQuery):
    target_id = int(callback.data.split(":")[1])
    await db.ensure_user(target_id)
    await db.increment(target_id, "praised")
    try:
        await bot.send_message(target_id, f"✨ {callback.from_user.full_name} похвалил(а) тебя!")
    except Exception:
        pass
    await callback.answer("Отправлено!")
    await callback.message.edit_reply_markup(reply_markup=None)

@dp.callback_query(F.data == "break_pair")
async def break_pair_cb(callback: types.CallbackQuery):
    uid = callback.from_user.id
    user = await db.get_user(uid)
    if not user or not user["paired"]:
        await callback.answer("Ты не в паре.", show_alert=True)
        return
    partner_id = await db.unlink_pair(uid)
    try:
        if partner_id:
            await bot.send_message(partner_id, "💔 Твой партнёр разорвал пару.")
    except Exception:
        pass
    await callback.message.edit_text("💔 Пара разорвана.")
    await callback.message.answer("Главное меню:", reply_markup=get_main_keyboard())
    await callback.answer()

async def send_request(message: types.Message, what: str):
    uid = message.from_user.id
    data = await db.ensure_user(uid)
    if not data["paired"]:
        await message.answer("Сначала пригласи партнёра.", reply_markup=get_main_keyboard())
        return
    try:
        await bot.send_message(data["partner_id"], f"🔔 Твой партнёр просит тебя {what}!")
        await message.answer("Запрос отправлен!", reply_markup=get_main_keyboard())
    except Exception:
        await message.answer("Не удалось отправить.", reply_markup=get_main_keyboard())

async def main():
    from aiohttp import web
    await db.init_pool()
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception:
        pass

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
