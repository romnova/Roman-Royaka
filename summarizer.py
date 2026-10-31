"""AI-підсумок переписки через Claude API."""

from datetime import datetime

from anthropic import AsyncAnthropic

from storage import StoredMessage

MODEL = "claude-opus-5-5"
# Скільки символів переписки максимум відправляти в один запит
MAX_CHARS = 400_000

SYSTEM_PROMPT = (
    "Ти робиш підсумки переписки з Telegram-групи для її учасника. "
    "Пиши українською, коротко і по суті. Структура:\n"
    "1. Головні теми (2–6 пунктів).\n"
    "2. Рішення та домовленості.\n"
    "3. Питання без відповіді та задачі, хто за що взявся.\n"
    "4. Важливі дати, посилання, цифри.\n"
    "Пропускай розділ, якщо для нього нічого немає. Не вигадуй того, чого немає в переписці. "
    "Форматуй простим текстом без Markdown-розмітки, пункти позначай «•»."
)


def format_transcript(messages: list[StoredMessage]) -> tuple[str, int]:
    """Перетворює повідомлення на текст. Повертає (текст, скільки повідомлень увійшло).

    Якщо переписка більша за MAX_CHARS, береться її найновіша частина.
    """
    lines: list[str] = []
    total = 0
    for m in reversed(messages):
        when = datetime.fromtimestamp(m.date).strftime("%d.%m %H:%M")
        author = f"{m.full_name} (@{m.username})" if m.username else m.full_name
        line = f"[{when}] {author}: {m.text}"
        if total + len(line) > MAX_CHARS and lines:
            break
        lines.append(line)
        total += len(line) + 1
    lines.reverse()
    return "\n".join(lines), len(lines)


class Summarizer:
    def __init__(self, api_key: str):
        self.client = AsyncAnthropic(api_key=api_key)

    async def summarize(self, chat_title: str, messages: list[StoredMessage]) -> tuple[str, int]:
        """Повертає (текст підсумку, кількість повідомлень, що увійшли в підсумок)."""
        transcript, used = format_transcript(messages)
        response = await self.client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            output_config={"effort": "low"},
            # Якщо модель відмовить через фільтри безпеки, API сам повторить запит на іншій моделі
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[
                {
                    "role": "user",
                    "content": f"Група: {chat_title}\n\n<transcript>\n{transcript}\n</transcript>",
                }
            ],
        )
        if response.stop_reason == "refusal":
            return "Claude відмовився робити підсумок цієї переписки.", used
        text = "".join(block.text for block in response.content if block.type == "text").strip()
        return text or "Порожня відповідь від Claude.", used
