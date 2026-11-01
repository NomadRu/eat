import asyncio
import os
import logging
import secrets
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
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
    b.button(text="🍰 Я поел(а)")
    b.button(text="🥤 Я попил(а)")
    b.button(text="🎀 Мой профиль")
    b.button(text="🌸 Статистика")
    b.button(text="💌 Попросить")
    b.button(text="🔗 Пригласить")
    b.adjust(2, 2, 2)
    return b.as_markup(resize_keyboard=True)

def get_request_keyboard():
    b = ReplyKeyboardBuilder()
    b.button(text="Попросить покушать 🍓")
    b.button(text="Попросить водички 💦")
    b.button(text="Назад")
    b.adjust(2, 1)
    return b.as_markup(resize_keyboard=True)

def get_praise_keyboard(target_id):
    b = InlineKeyboardBuilder()
    b.button(text="💖 Похвалить", callback_data=f"praise:{target_id}")
    b.button(text="🤗 Обнять", callback_data=f"hug:{target_id}")
    return b.as_markup()

def get_refuse_keyboard():
    b = InlineKeyboardBuilder()
    b.button(text="🙅‍♀️ Я не хочу кушать", callback_data="refuse_food")
    return b.as_markup()

def get_invite_keyboard(link):
    b = InlineKeyboardBuilder()
    b.button(text="💌 Отправить ссылку", url=f"https://t.me/share/url?url={link}&text=Присоединяйся ко мне, будем следить за едой вместе! 🥰")
    return b.as_markup()

def get_stats_keyboard():
    b = InlineKeyboardBuilder()
    b.button(text="💔 Разорвать пару", callback_data="break_pair")
    return b.as_markup()

def get_cancel_keyboard():
    b = ReplyKeyboardBuilder()
    b.button(text="Отмена")
    return b.as_markup(resize_keyboard=True)

@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    await db.ensure_user(uid)
    user = await db.get_user(uid)

    if user["paired"]:
        await message.answer("✨ <b>С возвращением!</b> Выбери действие:", parse_mode="HTML", reply_markup=get_main_keyboard())
        return

    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        code = args[1].strip()
        inviter_id = await db.pop_invite(code)
        if not inviter_id:
            await message.answer("❌ Ссылка недействительна или устарела.", reply_markup=get_main_keyboard())
            return
        if inviter_id == uid:
            await message.answer("😅 Нельзя связать себя с собой.", reply_markup=get_main_keyboard())
            return
        inviter = await db.get_user(inviter_id)
        if not inviter:
            await message.answer("❌ Приглашение недействительно.", reply_markup=get_main_keyboard())
            return
        if inviter["paired"] or user["paired"]:
            await message.answer("⚠️ Один из вас уже состоит в паре.", reply_markup=get_main_keyboard())
            return
        await db.set_partner(uid, inviter_id)
        try:
            await bot.send_message(inviter_id, f"🎉 <b>{message.from_user.full_name}</b> присоединился(ась) к тебе! Теперь вы пара 🥰", parse_mode="HTML")
        except Exception:
            pass
        await message.answer("💖 <b>Вы успешно связаны!</b> Теперь вы пара.", parse_mode="HTML", reply_markup=get_main_keyboard())
        return

    await message.answer(
        "Приветик! 💕\n\nНажми <b>«🔗 Пригласить»</b>, чтобы отправить ссылку своему партнеру и начать вести учёт вместе.",
        parse_mode="HTML", reply_markup=get_main_keyboard()
    )

@dp.message((F.text == "🎀 Мой профиль") | (F.text.lower() == "профиль"))
async def show_profile(message: types.Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    try:
        data = await db.ensure_user(uid)
        if not data["paired"]:
            await message.answer("🥺 Ты пока не в паре. Нажми «🔗 Пригласить».", reply_markup=get_main_keyboard())
            return

        pdata = await db.get_user(data["partner_id"]) or {"eaten": 0, "drunk": 0, "praised": 0}

        text = (
            f"🎀 <b>Твой профиль за сегодня</b>\n"
            f"┣ 🍰 Поел(а): <code>{data['eaten']}</code>\n"
            f"┣ 🥤 Попил(а): <code>{data['drunk']}</code>\n"
            f"┗ 💖 Похвал: <code>{data['praised']}</code>\n\n"
            f"👥 <b>Партнёр за сегодня</b>\n"
            f"┣ 🍰 Поел(а): <code>{pdata['eaten']}</code>\n"
            f"┣ 🥤 Попил(а): <code>{pdata['drunk']}</code>\n"
            f"┗ 💖 Похвал: <code>{pdata['praised']}</code>"
        )
        await message.answer(text, parse_mode="HTML", reply_markup=get_main_keyboard())
    except Exception as e:
        await message.answer(f"⚠️ Ошибка БД: {e}", reply_markup=get_main_keyboard())

@dp.message((F.text == "🌸 Статистика") | (F.text.lower() == "статистика"))
async def couple_stats(message: types.Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    try:
        data = await db.ensure_user(uid)
        if not data["paired"]:
            await message.answer("🌸 Статистика доступна только в паре.", reply_markup=get_main_keyboard())
            return

        pdata = await db.get_user(data["partner_id"]) or {"eaten": 0, "drunk": 0, "praised": 0}
        text = (
            f"🌸 <b>Статистика вашей пары за сегодня</b> 🌸\n\n"
            f"🍽️ Вы вместе съели: <b>{data['eaten'] + pdata['eaten']}</b> раз\n"
            f"💧 Вы вместе выпили: <b>{data['drunk'] + pdata['drunk']}</b> раз\n"
            f"💕 Вы похвалили друг друга: <b>{data['praised'] + pdata['praised']}</b> раз\n\n"
            f"<i>Вы огромные молодцы! Так держать 💪💗</i>"
        )
        await message.answer(text, parse_mode="HTML", reply_markup=get_stats_keyboard())
    except Exception as e:
        await message.answer(f"⚠️ Ошибка БД: {e}", reply_markup=get_main_keyboard())

@dp.message((F.text == "🔗 Пригласить") | (F.text.lower() == "пригласить"))
async def invite_partner(message: types.Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    user = await db.ensure_user(uid)
    if user["paired"]:
        await message.answer("Ты уже в паре 💕", reply_markup=get_main_keyboard())
        return

    code = secrets.token_urlsafe(8)
    await db.create_invite(code, uid)
    bot_username = (await bot.get_me()).username
    link = f"https://t.me/{bot_username}?start={code}"
    await message.answer(f"Вот твоя ссылка-приглашение:\n\n<code>{link}</code>\n\nОтправь её партнёру 💌", parse_mode="HTML", reply_markup=get_invite_keyboard(link))

@dp.message((F.text == "💌 Попросить") | (F.text.lower() == "попросить"))
async def ask_partner(message: types.Message, state: FSMContext):
    await state.clear()
    data = await db.ensure_user(message.from_user.id)
    if not data["paired"]:
        await message.answer("Сначала пригласи партнёра.", reply_markup=get_main_keyboard())
        return
    await message.answer("Что попросить? 🥺", reply_markup=get_request_keyboard())

@dp.message((F.text == "Попросить покушать 🍓") | (F.text.lower() == "покушать"))
async def request_food(message: types.Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    data = await db.ensure_user(uid)
    if not data["paired"]:
        await message.answer("Сначала пригласи партнёра.", reply_markup=get_main_keyboard())
        return
    try:
        await bot.send_message(
            data["partner_id"], 
            f"🔔 Твой партнёр просит тебя покушать 🍓", 
            reply_markup=get_refuse_keyboard()
        )
        await db.add_reminder(data["partner_id"], message.from_user.full_name, "покушать 🍓")
        await message.answer("Запрос отправлен! 💌", reply_markup=get_main_keyboard())
    except Exception:
        await message.answer("Не удалось отправить.", reply_markup=get_main_keyboard())

@dp.message((F.text == "Попросить водички 💦") | (F.text.lower() == "водички"))
async def request_water(message: types.Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    data = await db.ensure_user(uid)
    if not data["paired"]:
        await message.answer("Сначала пригласи партнёра.", reply_markup=get_main_keyboard())
        return
    try:
        await bot.send_message(
            data["partner_id"], 
            f"🔔 Твой партнёр просит тебя водички 💦", 
            reply_markup=get_refuse_keyboard()
        )
        await db.add_reminder(data["partner_id"], message.from_user.full_name, "водички 💦")
        await message.answer("Запрос отправлен! 💌", reply_markup=get_main_keyboard())
    except Exception:
        await message.answer("Не удалось отправить.", reply_markup=get_main_keyboard())

@dp.message((F.text == "Назад") | (F.text.lower() == "назад"))
async def back_to_menu(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Главное меню", reply_markup=get_main_keyboard())

@dp.message((F.text == "🍰 Я поел(а)") | (F.text.lower() == "поел"))
async def ate_food(message: types.Message, state: FSMContext):
    await state.clear()
    await db.ensure_user(message.from_user.id)
    await state.set_state(InputStates.waiting_for_food)
    await message.answer("Что ты скушал(а)? Напиши текстом или отправь фото 📸", reply_markup=get_cancel_keyboard())

@dp.message((F.text == "🥤 Я попил(а)") | (F.text.lower() == "попил"))
async def drank_water(message: types.Message, state: FSMContext):
    await state.clear()
    await db.ensure_user(message.from_user.id)
    await state.set_state(InputStates.waiting_for_water)
    await message.answer("Что ты выпил(а)? Напиши текстом или отправь фото 💧", reply_markup=get_cancel_keyboard())

@dp.message((F.text == "Отмена") | (F.text.lower() == "отмена"))
async def cancel_input(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Действие отменено.", reply_markup=get_main_keyboard())

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
            await bot.send_photo(chat_id=user["partner_id"], photo=message.photo[-1].file_id, caption=f"🍰 <b>{message.from_user.full_name}</b> поел(а)!", parse_mode="HTML", reply_markup=get_praise_keyboard(uid))
        else:
            await bot.send_message(chat_id=user["partner_id"], text=f"🍰 <b>{message.from_user.full_name}</b> поел(а): <i>{content}</i>", parse_mode="HTML", reply_markup=get_praise_keyboard(uid))
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
            await bot.send_photo(chat_id=user["partner_id"], photo=message.photo[-1].file_id, caption=f"🥤 <b>{message.from_user.full_name}</b> попил(а)!", parse_mode="HTML", reply_markup=get_praise_keyboard(uid))
        else:
            await bot.send_message(chat_id=user["partner_id"], text=f"🥤 <b>{message.from_user.full_name}</b> попил(а): <i>{content}</i>", parse_mode="HTML", reply_markup=get_praise_keyboard(uid))
    except Exception:
        pass

@dp.callback_query(F.data.startswith("praise:"))
async def process_praise(callback: types.CallbackQuery):
    target_id = int(callback.data.split(":")[1])
    await db.ensure_user(target_id)
    await db.increment(target_id, "praised")
    try:
        await bot.send_message(target_id, f"💖 <b>{callback.from_user.full_name}</b> похвалил(а) тебя! Так держать! ✨", parse_mode="HTML")
    except Exception:
        pass
    await callback.answer("Похвала отправлена! 💕")
    await callback.message.edit_reply_markup(reply_markup=None)

@dp.callback_query(F.data.startswith("hug:"))
async def process_hug(callback: types.CallbackQuery):
    target_id = int(callback.data.split(":")[1])
    try:
        await bot.send_message(target_id, f"🤗 <b>{callback.from_user.full_name}</b> крепко обнял(а) тебя! 🥰", parse_mode="HTML")
    except Exception:
        pass
    await callback.answer("Обнимашки отправлены! 🤗")
    await callback.message.edit_reply_markup(reply_markup=None)

@dp.callback_query(F.data == "refuse_food")
async def process_refuse_food(callback: types.CallbackQuery):
    # Отвечаем тому, кто нажал
    await callback.answer("Нельзя не есть, когда любимый человек просит, надо кушать! 🥺", show_alert=True)
    
    # Ищем, кто его попросил (это сложно сделать без хранения истории, поэтому просто шлем сообщение партнеру)
    user = await db.get_user(callback.from_user.id)
    if user and user["partner_id"]:
        try:
            await bot.send_message(user["partner_id"], f"🥺 <b>{callback.from_user.full_name}</b> говорит, что не хочет кушать... Но мы-то знаем, что надо! Переубеди его(её) 💕", parse_mode="HTML")
        except Exception:
            pass

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

# Фоновая задача для напоминаний
async def reminder_worker():
    while True:
        try:
            due = await db.get_due_reminders()
            for r in due:
                try:
                    await bot.send_message(r["target_id"], f"⏰ Напоминание: <b>{r['sender_name']}</b> 30 минут назад просил(а) тебя {r['message']}!\n\n<i>Не забудь покушать и попить 💕</i>", parse_mode="HTML")
                except Exception:
                    pass
        except Exception as e:
            logging.error(f"Reminder worker error: {e}")
        await asyncio.sleep(30) # Проверяем каждые 30 секунд

async def main():
    from aiohttp import web
    await db.init_pool()
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception:
        pass

    # Запускаем фоновую задачу
    asyncio.create_task(reminder_worker())

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
