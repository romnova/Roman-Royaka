"""Telegram-бот, який збирає повідомлення з груп і робить підсумки та експорт."""

import asyncio
import html
import logging
import os

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, CommandObject
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from dotenv import load_dotenv

from exporter import SheetsExporter, to_csv
from storage import Storage, StoredMessage
from summarizer import Summarizer

load_dotenv()

BOT_TOKEN = os.environ["BOT_TOKEN"]
OWNER_ID = int(os.environ.get("OWNER_ID") or 0)
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
GOOGLE_CREDENTIALS_FILE = os.environ.get("GOOGLE_CREDENTIALS_FILE", "")
GOOGLE_SPREADSHEET_ID = os.environ.get("GOOGLE_SPREADSHEET_ID", "")
DB_PATH = os.environ.get("DB_PATH", "messages.db")
DEFAULT_HOURS = 24

TG_LIMIT = 4000  # ліміт Telegram — 4096 символів на повідомлення

storage = Storage(DB_PATH)
summarizer = Summarizer(ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None
sheets: SheetsExporter | None = None

router = Router()


# ---------- Збір повідомлень з груп ----------

def _store(message: Message) -> None:
    text = message.text or message.caption
    if not text:
        return
    user = message.from_user
    storage.save(
        StoredMessage(
            chat_id=message.chat.id,
            chat_title=message.chat.title or str(message.chat.id),
            message_id=message.message_id,
            user_id=user.id if user else None,
            username=user.username if user else None,
            full_name=user.full_name if user else (message.sender_chat.title if message.sender_chat else "?"),
            text=text,
            date=int(message.date.timestamp()),
        )
    )


@router.message(F.chat.type.in_({"group", "supergroup"}))
async def collect(message: Message) -> None:
    _store(message)


@router.edited_message(F.chat.type.in_({"group", "supergroup"}))
async def collect_edited(message: Message) -> None:
    _store(message)


# ---------- Команди власника (в особистому чаті з ботом) ----------

def is_owner(user_id: int | None) -> bool:
    return OWNER_ID != 0 and user_id == OWNER_ID


private = F.chat.type == "private"


@router.message(Command("start"), private)
async def cmd_start(message: Message) -> None:
    if not is_owner(message.from_user.id):
        await message.answer(
            f"Ваш Telegram ID: <code>{message.from_user.id}</code>\n"
            "Щоб керувати ботом, впишіть його в OWNER_ID у файлі .env і перезапустіть бота."
        )
        return
    await message.answer(
        "Я збираю повідомлення з груп, куди мене додали.\n\n"
        "/chats — список чатів\n"
        "/summary [години] — AI-підсумок (за замовчуванням за 24 год)\n"
        "/export [години] — CSV-файл\n"
        "/sheets [години] — вивантажити в Google Sheets\n\n"
        "Години = 0 означає «за весь час»."
    )


@router.message(Command("chats"), private)
async def cmd_chats(message: Message) -> None:
    if not is_owner(message.from_user.id):
        return
    chats = storage.chats()
    if not chats:
        await message.answer("Поки що немає зібраних повідомлень. Додайте мене в групу.")
        return
    lines = [f"• {html.escape(title)} — {count} повідомл." for _, title, count in chats]
    await message.answer("Зібрані чати:\n" + "\n".join(lines))


def _parse_hours(command: CommandObject) -> float | None:
    if not command.args:
        return DEFAULT_HOURS
    try:
        return max(float(command.args.strip().replace(",", ".")), 0)
    except ValueError:
        return None


async def _ask_chat(message: Message, command: CommandObject, action: str) -> None:
    if not is_owner(message.from_user.id):
        return
    hours = _parse_hours(command)
    if hours is None:
        await message.answer("Вкажіть кількість годин числом, наприклад: /summary 48")
        return
    chats = storage.chats()
    if not chats:
        await message.answer("Поки що немає зібраних повідомлень.")
        return
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"{title} ({count})", callback_data=f"{action}:{chat_id}:{hours:g}")]
            for chat_id, title, count in chats[:30]
        ]
    )
    period = "весь час" if hours == 0 else f"останні {hours:g} год"
    await message.answer(f"Оберіть чат (період: {period}):", reply_markup=keyboard)


@router.message(Command("summary"), private)
async def cmd_summary(message: Message, command: CommandObject) -> None:
    if summarizer is None:
        await message.answer("Не задано ANTHROPIC_API_KEY у .env — підсумки недоступні.")
        return
    await _ask_chat(message, command, "sum")


@router.message(Command("export"), private)
async def cmd_export(message: Message, command: CommandObject) -> None:
    await _ask_chat(message, command, "csv")


@router.message(Command("sheets"), private)
async def cmd_sheets(message: Message, command: CommandObject) -> None:
    if not (GOOGLE_CREDENTIALS_FILE and GOOGLE_SPREADSHEET_ID):
        await message.answer("Google Sheets не налаштовано: задайте GOOGLE_CREDENTIALS_FILE і GOOGLE_SPREADSHEET_ID у .env.")
        return
    await _ask_chat(message, command, "gs")


@router.callback_query(F.data.regexp(r"^(sum|csv|gs):-?\d+:[\d.]+$"))
async def on_chat_chosen(callback: CallbackQuery) -> None:
    global sheets
    if not is_owner(callback.from_user.id):
        await callback.answer()
        return
    action, chat_id_str, hours_str = callback.data.split(":")
    chat_id, hours = int(chat_id_str), float(hours_str)
    await callback.answer()

    messages = storage.messages(chat_id, hours or None)
    if not messages:
        await callback.message.edit_text("За цей період повідомлень немає.")
        return
    title = messages[-1].chat_title

    if action == "csv":
        await callback.message.answer_document(
            BufferedInputFile(to_csv(messages), filename=f"chat_{chat_id}.csv"),
            caption=f"{html.escape(title)}: {len(messages)} повідомл.",
        )
        return

    if action == "gs":
        await callback.message.edit_text("Вивантажую в Google Sheets…")
        try:
            if sheets is None:
                sheets = await asyncio.to_thread(SheetsExporter, GOOGLE_CREDENTIALS_FILE, GOOGLE_SPREADSHEET_ID)
            url = await asyncio.to_thread(sheets.export, title, chat_id, messages)
        except Exception as e:  # помилки доступу, квоти тощо — показуємо власнику
            logging.exception("Google Sheets export failed")
            await callback.message.edit_text(f"Помилка Google Sheets: {html.escape(str(e))}")
            return
        await callback.message.edit_text(f"Готово: {len(messages)} повідомл.\n{url}")
        return

    await callback.message.edit_text(f"Роблю підсумок «{html.escape(title)}» ({len(messages)} повідомл.)…")
    try:
        summary, used = await summarizer.summarize(title, messages)
    except Exception as e:
        logging.exception("Summary failed")
        await callback.message.edit_text(f"Помилка Claude API: {html.escape(str(e))}")
        return
    note = "" if used == len(messages) else f"\n(переписка завелика — взято останні {used} з {len(messages)} повідомл.)"
    await callback.message.edit_text(f"<b>Підсумок: {html.escape(title)}</b>{note}")
    # Сам підсумок — простим текстом, щоб розбиття на частини не зламало HTML-розмітку
    for i in range(0, len(summary), TG_LIMIT):
        await callback.message.answer(summary[i : i + TG_LIMIT], parse_mode=None)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    if not OWNER_ID:
        logging.warning("OWNER_ID не задано: напишіть боту /start, щоб дізнатися свій ID")
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher()
    dp.include_router(router)
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
