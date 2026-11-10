"""Демо-бот для приёма заявок.

Клиент: /start -> «Оставить заявку» -> имя -> телефон -> услуга -> комментарий -> подтверждение.
Владелец (ADMIN_ID): получает каждую заявку в личку, команда /leads — последние 10 заявок.
"""
import asyncio
import logging
import os
import re
from html import escape

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from dotenv import load_dotenv

import db

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# Услуги вынесены в словарь — под нового клиента меняешь только его.
SERVICES = {
    "consult": "Консультация",
    "repair": "Ремонт",
    "delivery": "Доставка",
    "other": "Другое",
}

router = Router()


# ---------- Состояния анкеты (FSM) ----------
class LeadForm(StatesGroup):
    name = State()
    phone = State()
    service = State()
    comment = State()
    confirm = State()


# ---------- Клавиатуры ----------
main_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="📝 Оставить заявку")],
              [KeyboardButton(text="ℹ️ О нас")]],
    resize_keyboard=True,
)

phone_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="📱 Отправить мой номер", request_contact=True)],
              [KeyboardButton(text="❌ Отмена")]],
    resize_keyboard=True,
)

cancel_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="❌ Отмена")]],
    resize_keyboard=True,
)

services_kb = InlineKeyboardMarkup(
    inline_keyboard=[[InlineKeyboardButton(text=title, callback_data=f"svc:{key}")]
                     for key, title in SERVICES.items()]
)

confirm_kb = InlineKeyboardMarkup(
    inline_keyboard=[[
        InlineKeyboardButton(text="✅ Отправить", callback_data="confirm:yes"),
        InlineKeyboardButton(text="✏️ Заново", callback_data="confirm:no"),
    ]]
)


# ---------- Общие команды ----------
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        f"Здравствуйте, {escape(message.from_user.first_name)}! 👋\n"
        "Я помогу оставить заявку — менеджер свяжется с вами.",
        reply_markup=main_kb,
    )


@router.message(F.text == "ℹ️ О нас")
async def about(message: Message):
    await message.answer(
        "Мы — сервисная компания. Работаем ежедневно с 9:00 до 21:00.\n"
        "Оставьте заявку, и мы перезвоним в течение 15 минут.",
        reply_markup=main_kb,
    )


# Отмена работает на любом шаге анкеты
@router.message(Command("cancel"))
@router.message(F.text == "❌ Отмена")
async def cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Заявка отменена.", reply_markup=main_kb)


# ---------- Анкета ----------
@router.message(F.text == "📝 Оставить заявку")
async def start_form(message: Message, state: FSMContext):
    await state.set_state(LeadForm.name)
    await message.answer("Как к вам обращаться?", reply_markup=cancel_kb)


@router.message(LeadForm.name, F.text)
async def get_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if not 2 <= len(name) <= 50:
        await message.answer("Введите имя от 2 до 50 символов.")
        return
    await state.update_data(name=name)
    await state.set_state(LeadForm.phone)
    await message.answer(
        "Ваш номер телефона? Нажмите кнопку или введите вручную.",
        reply_markup=phone_kb,
    )


@router.message(LeadForm.phone, F.contact)
async def get_phone_contact(message: Message, state: FSMContext):
    await save_phone(message, state, message.contact.phone_number)


@router.message(LeadForm.phone, F.text)
async def get_phone_text(message: Message, state: FSMContext):
    digits = re.sub(r"\D", "", message.text)
    if not 10 <= len(digits) <= 15:
        await message.answer("Похоже, номер неверный. Пример: +7 999 123-45-67")
        return
    await save_phone(message, state, message.text.strip())


async def save_phone(message: Message, state: FSMContext, phone: str):
    await state.update_data(phone=phone)
    await state.set_state(LeadForm.service)
    # Убираем reply-клавиатуру и показываем inline-кнопки услуг
    await message.answer("Отлично!", reply_markup=ReplyKeyboardRemove())
    await message.answer("Какая услуга вас интересует?", reply_markup=services_kb)


@router.callback_query(LeadForm.service, F.data.startswith("svc:"))
async def get_service(callback: CallbackQuery, state: FSMContext):
    key = callback.data.split(":", 1)[1]
    service = SERVICES.get(key, "Другое")
    await state.update_data(service=service)
    await state.set_state(LeadForm.comment)
    await callback.message.edit_text(f"Услуга: <b>{service}</b>")
    await callback.message.answer(
        "Опишите задачу в паре слов (или отправьте «-», если нечего добавить).",
        reply_markup=cancel_kb,
    )
    await callback.answer()


@router.message(LeadForm.comment, F.text)
async def get_comment(message: Message, state: FSMContext):
    comment = "" if message.text.strip() == "-" else message.text.strip()[:500]
    await state.update_data(comment=comment)
    await state.set_state(LeadForm.confirm)
    data = await state.get_data()
    await message.answer("Проверьте заявку:", reply_markup=ReplyKeyboardRemove())
    await message.answer(format_lead(data), reply_markup=confirm_kb)


@router.callback_query(LeadForm.confirm, F.data == "confirm:no")
async def restart_form(callback: CallbackQuery, state: FSMContext):
    await state.set_state(LeadForm.name)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Начнём заново. Как к вам обращаться?",
                                  reply_markup=cancel_kb)
    await callback.answer()


@router.callback_query(LeadForm.confirm, F.data == "confirm:yes")
async def send_lead(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    user = callback.from_user
    lead_id = db.add_lead(user.id, user.username, data["name"], data["phone"],
                          data["service"], data["comment"])
    await state.clear()

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        f"Спасибо! Заявка №{lead_id} принята, скоро с вами свяжемся. 🙌",
        reply_markup=main_kb,
    )
    await callback.answer()

    # Уведомление владельцу
    if ADMIN_ID:
        contact = f"@{user.username}" if user.username else f"id {user.id}"
        await bot.send_message(
            ADMIN_ID,
            f"🔔 <b>Новая заявка №{lead_id}</b>\n"
            f"{format_lead(data)}\nTelegram: {escape(contact)}",
        )


# Если на шаге с кнопками пишут текст — подсказываем
@router.message(LeadForm.service)
@router.message(LeadForm.confirm)
async def use_buttons(message: Message):
    await message.answer("Пожалуйста, выберите вариант кнопкой выше 👆")


def format_lead(data: dict) -> str:
    lines = [
        f"👤 Имя: {escape(data['name'])}",
        f"📞 Телефон: {escape(data['phone'])}",
        f"🛠 Услуга: {escape(data['service'])}",
    ]
    if data.get("comment"):
        lines.append(f"💬 Комментарий: {escape(data['comment'])}")
    return "\n".join(lines)


# ---------- Админ ----------
@router.message(Command("leads"), F.from_user.id == ADMIN_ID)
async def show_leads(message: Message):
    rows = db.last_leads()
    if not rows:
        await message.answer("Заявок пока нет.")
        return
    text = "\n".join(
        f"№{lid} · {created} · {escape(name)} · {escape(phone)} · {escape(svc)}"
        for lid, name, phone, svc, created in rows
    )
    await message.answer(f"<b>Последние заявки:</b>\n{text}")


# ---------- Запуск ----------
async def main():
    if not BOT_TOKEN:
        raise SystemExit("Не найден BOT_TOKEN. Создай файл .env по примеру .env.example")
    logging.basicConfig(level=logging.INFO)
    db.init_db()
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
