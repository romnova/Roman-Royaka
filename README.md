# Telegram-бот для збору інформації з чатів

Бот читає повідомлення в групах, куди ви його додали, зберігає їх у локальну базу SQLite і за командою:

- робить **AI-підсумок** переписки через Claude («що обговорювали за добу»);
- вивантажує повідомлення у **CSV** (відкривається в Excel);
- вивантажує повідомлення в **Google Sheets**.

Керувати ботом може тільки власник (`OWNER_ID`), в особистому чаті з ботом.

## 1. Створіть бота

1. Напишіть [@BotFather](https://t.me/BotFather) команду `/newbot` і скопіюйте токен.
2. **Важливо:** там же виконайте `/setprivacy` → оберіть бота → **Disable**.
   Без цього бот у групах бачить лише команди, а не всі повідомлення.
   (Якщо бота вже додали в групу до цього кроку, видаліть його з групи й додайте знову.)

## 2. Встановлення

Потрібен Python 3.10+.

```bash
git clone https://github.com/romnova/Roman-Royaka.git
cd Roman-Royaka
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements.txt
```

Скопіюйте `.env.example` у `.env` і заповніть:

| Змінна | Що це |
|---|---|
| `BOT_TOKEN` | токен від @BotFather |
| `OWNER_ID` | ваш Telegram ID: запустіть бота, напишіть йому `/start`, він його покаже |
| `ANTHROPIC_API_KEY` | ключ з [console.anthropic.com](https://console.anthropic.com/settings/keys), потрібен для `/summary` |
| `GOOGLE_CREDENTIALS_FILE`, `GOOGLE_SPREADSHEET_ID` | необов'язково, для `/sheets` (див. нижче) |

## 3. Запуск

```bash
python bot.py
```

Додайте бота в потрібні групи. Бот збирає повідомлення лише поки він запущений;
старішу історію Telegram ботам не віддає.

## Команди (в особистому чаті з ботом)

| Команда | Що робить |
|---|---|
| `/start` | довідка (або ваш ID, якщо `OWNER_ID` ще не задано) |
| `/chats` | список чатів і кількість зібраних повідомлень |
| `/summary [години]` | AI-підсумок, за замовчуванням за 24 год; `/summary 0` — за весь час |
| `/export [години]` | CSV-файл з повідомленнями |
| `/sheets [години]` | вивантаження в Google Sheets |

Після команди бот покаже кнопки з чатами, натисніть потрібний.

## Налаштування Google Sheets (необов'язково)

1. У [Google Cloud Console](https://console.cloud.google.com/) створіть проєкт і увімкніть
   **Google Sheets API** та **Google Drive API**.
2. Створіть **Service Account** → вкладка Keys → *Add key* → JSON. Збережіть файл у папку бота
   як `google-credentials.json`.
3. Створіть таблицю в Google Sheets і надайте доступ «Редактор» на email сервісного акаунта
   (поле `client_email` у JSON-файлі).
4. Скопіюйте ID таблиці (частина посилання між `/d/` і `/edit`) у `GOOGLE_SPREADSHEET_ID`.

Кожен чат вивантажується в окремий аркуш; повторний експорт перезаписує аркуш.

## Файли

- `bot.py` — сам бот (aiogram 3)
- `storage.py` — збереження повідомлень у SQLite
- `summarizer.py` — підсумки через Claude API
- `exporter.py` — CSV та Google Sheets

## Приватність

Повідомлення зберігаються тільки у вас на комп'ютері (`messages.db`). Для підсумку переписка
за обраний період надсилається в Claude API. Варто попередити учасників групи, що бот
зберігає повідомлення.
