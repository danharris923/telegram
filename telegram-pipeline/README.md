# Telegram Posting Pipeline

Automated pipeline that reads links from a Google Sheet and posts them to a Telegram channel, one at a time. Designed to run as a cron job.

## How It Works

Each run:
1. Reads the first row from the Google Sheet
2. Sends the link to your Telegram channel
3. Deletes that row from the sheet (so the next row becomes first)
4. Exits — next cron run picks up the new first row

## Prerequisites

- Python 3.10+
- A Google Cloud service account with Sheets API enabled
- A Telegram bot (created via BotFather)
- A Telegram channel with the bot added as admin

## Setup

### 1. Google Cloud Service Account

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a project or use an existing one
3. Enable **Google Sheets API** and **Google Drive API**
4. Go to IAM & Admin → Service Accounts → Create Service Account
5. Create a JSON key and download it
6. Share your Google Sheet with the service account email (Editor access)

### 2. Telegram Bot

1. Open Telegram and search for `@BotFather`
2. Send `/newbot` and follow the prompts
3. Copy the bot token

### 3. Telegram Channel

1. Create a channel in Telegram
2. Go to channel Settings → Administrators → Add Administrator
3. Add your bot and give it permission to post messages

### 4. Environment Variables

Copy `.env.example` to `.env` and fill in your values:

```
TELEGRAM_BOT_TOKEN=1234567890:AAHxyz...
TELEGRAM_CHANNEL_ID=@your_channel_name
GOOGLE_CREDENTIALS_JSON_PATH=/path/to/service-account.json
GOOGLE_SHEET_ID=1a2b3c4d5e6f...
GOOGLE_SHEET_NAME=Sheet1
GOOGLE_SHEET_LINK_COLUMN=A
```

### 5. Install Dependencies

```bash
pip install -r requirements.txt
```

### 6. Test Manually

```bash
python main.py
```

You should see colorful console output showing each step.

### 7. Set Up Cron (every 3 hours)

```bash
crontab -e
```

Add this line:

```
0 */3 * * * cd /path/to/telegram-pipeline && /usr/bin/python3 main.py >> /var/log/telegram-pipeline.log 2>&1
```

This runs at minute 0 of every 3rd hour (00:00, 03:00, 06:00, ...).

## Google Sheet Format

| Column A (Links)              |
|-------------------------------|
| https://example.com/deal1     |
| https://example.com/deal2     |
| https://example.com/deal3     |

- Column A: the links/content to post
- After posting, the first row is deleted and all rows shift up

## Troubleshooting

- **"Bot token is invalid"** — Regenerate the token via BotFather `/revoke` then `/newbot`
- **"Channel is invalid"** — Make sure the bot is added as an admin to the channel
- **"Failed to open spreadsheet"** — Share the sheet with the service account email
- **"No rows remaining"** — The sheet is empty. Add more links.
- **"MESSAGE WAS SENT BUT ROW WAS NOT DELETED"** — The Telegram post went through but the row delete failed. Manually delete the first row from the sheet.
