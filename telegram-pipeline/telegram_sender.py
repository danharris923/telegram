"""
telegram_sender.py — Sends messages to a Telegram channel via the Bot API.

Uses the requests library to call the Telegram Bot API directly.
Includes bot and channel validation, rate limiting, and verbose logging.

Imports: requests, time, config, logger
Exports: send_message(), validate_bot(), validate_channel()
"""

import time
import requests
from config import config
from logger import get_logger

log = get_logger("telegram_sender")

# Telegram Bot API base URL
API_BASE = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}"

# Rate limit: track the last time a message was sent
_last_send_time = 0


def validate_bot():
    """
    Verify the bot token is valid by calling /getMe.

    Returns True if the bot is valid, False otherwise.
    Does NOT raise exceptions — main.py decides what to do.
    """
    log.info("Validating Telegram bot token via /getMe...")
    try:
        response = requests.get(f"{API_BASE}/getMe", timeout=10)
        data = response.json()

        if data.get("ok"):
            bot_info = data["result"]
            log.success(f"Bot validated: @{bot_info['username']} (ID: {bot_info['id']})")
            return True
        else:
            log.error(f"Bot validation failed: {data.get('description', 'Unknown error')}")
            return False

    except Exception as e:
        log.error(f"Bot validation failed with exception: {e}")
        return False


def validate_channel():
    """
    Verify the channel is accessible by calling /getChat.

    Returns True if the channel exists and the bot can access it, False otherwise.
    Does NOT raise exceptions — main.py decides what to do.
    """
    log.info(f"Validating Telegram channel: {config.TELEGRAM_CHANNEL_ID}...")
    try:
        response = requests.get(
            f"{API_BASE}/getChat",
            params={"chat_id": config.TELEGRAM_CHANNEL_ID},
            timeout=10,
        )
        data = response.json()

        if data.get("ok"):
            chat_info = data["result"]
            title = chat_info.get("title", "N/A")
            log.success(f"Channel validated: {title}")
            return True
        else:
            log.error(f"Channel validation failed: {data.get('description', 'Unknown error')}")
            return False

    except Exception as e:
        log.error(f"Channel validation failed with exception: {e}")
        return False


def send_message(text):
    """
    Send a message to the Telegram channel.

    Uses parse_mode=HTML. Includes rate limiting (min 3 seconds between sends).
    Returns the API response dict on success.
    Raises an exception on failure.
    """
    global _last_send_time

    # Rate limit guard: ensure at least 3 seconds between sends
    now = time.time()
    elapsed = now - _last_send_time
    if _last_send_time > 0 and elapsed < 3:
        wait_time = 3 - elapsed
        log.warning(f"Rate limit: waiting {wait_time:.1f}s before sending...")
        time.sleep(wait_time)

    log.info(f"Sending message to channel {config.TELEGRAM_CHANNEL_ID}...")
    log.debug(f"Message content: {text[:100]}{'...' if len(text) > 100 else ''}")

    try:
        response = requests.post(
            f"{API_BASE}/sendMessage",
            json={
                "chat_id": config.TELEGRAM_CHANNEL_ID,
                "text": text,
                "parse_mode": "HTML",
            },
            timeout=15,
        )

        # Update the last send time
        _last_send_time = time.time()

        data = response.json()

        if data.get("ok"):
            message_id = data["result"]["message_id"]
            log.success(f"Message sent successfully! message_id={message_id}")
            return data
        else:
            error_desc = data.get("description", "Unknown error")
            log.error(f"Telegram API error: {error_desc}")
            log.error(f"Full response: {data}")
            raise Exception(f"Telegram API error: {error_desc}")

    except requests.ConnectionError as e:
        log.error(f"Connection error: {e}")
        raise
    except requests.Timeout as e:
        log.error(f"Request timed out: {e}")
        raise
