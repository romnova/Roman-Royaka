"""Експорт повідомлень у CSV та Google Sheets."""

import csv
import io
from datetime import datetime

from storage import StoredMessage

HEADER = ["Дата", "Автор", "Username", "User ID", "Message ID", "Текст"]


def _row(m: StoredMessage) -> list:
    return [
        datetime.fromtimestamp(m.date).strftime("%Y-%m-%d %H:%M:%S"),
        m.full_name,
        m.username or "",
        m.user_id or "",
        m.message_id,
        m.text,
    ]


def to_csv(messages: list[StoredMessage]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(HEADER)
    writer.writerows(_row(m) for m in messages)
    # utf-8-sig, щоб Excel правильно показав кирилицю
    return buf.getvalue().encode("utf-8-sig")


class SheetsExporter:
    """Пише кожен чат в окремий аркуш таблиці (аркуш перезаписується при кожному експорті)."""

    def __init__(self, credentials_file: str, spreadsheet_id: str):
        import gspread  # імпорт тут, щоб бот працював і без налаштованих Google Sheets

        self.spreadsheet = gspread.service_account(filename=credentials_file).open_by_key(spreadsheet_id)

    def export(self, chat_title: str, chat_id: int, messages: list[StoredMessage]) -> str:
        import gspread

        # Назва аркуша: до 100 символів, без символів, заборонених у Google Sheets
        title = f"{chat_title} ({chat_id})"
        for ch in "[]*?/\\:":
            title = title.replace(ch, " ")
        title = title[:100]

        try:
            ws = self.spreadsheet.worksheet(title)
            ws.clear()
        except gspread.WorksheetNotFound:
            ws = self.spreadsheet.add_worksheet(title=title, rows=len(messages) + 1, cols=len(HEADER))
        ws.update([HEADER] + [_row(m) for m in messages], value_input_option="RAW")
        return f"{self.spreadsheet.url}#gid={ws.id}"
