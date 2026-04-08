"""
config.py — Loads and validates all environment variables via python-dotenv.

Reads from .env file in the project root. Validates that every required
variable is present and exits with a red error if anything is missing.
Exposes a single `config` object (Config class instance) used by all modules.

Imports: os, sys, dotenv, logger
Exports: config (Config instance)
"""

import os
import sys
from dotenv import load_dotenv
from logger import get_logger

log = get_logger("config")

# Load environment variables from .env file in the same directory as this script
dotenv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(dotenv_path)


class Config:
    """Holds all configuration values loaded from environment variables."""

    def __init__(self):
        # List of all required environment variable names
        required_vars = [
            "TELEGRAM_BOT_TOKEN",
            "TELEGRAM_CHANNEL_ID",
            "GOOGLE_CREDENTIALS_JSON_PATH",
            "GOOGLE_SHEET_ID",
            "GOOGLE_SHEET_NAME",
            "GOOGLE_SHEET_LINK_COLUMN",
        ]

        # Load each required variable and fail loudly if any are missing
        missing = []
        for var_name in required_vars:
            value = os.environ.get(var_name)
            if not value:
                missing.append(var_name)
            else:
                setattr(self, var_name, value)

        # If any required variables are missing, print them all and exit
        if missing:
            log.error("The following required environment variables are missing:")
            for var_name in missing:
                log.error(f"  - {var_name}")
            log.error("Please add them to your .env file. See .env.example for reference.")
            sys.exit(1)

        # Log all loaded variables (mask the Telegram token for security)
        log.success("All environment variables loaded successfully:")
        masked_token = "***" + self.TELEGRAM_BOT_TOKEN[-6:]
        log.info(f"  TELEGRAM_BOT_TOKEN      = {masked_token}")
        log.info(f"  TELEGRAM_CHANNEL_ID     = {self.TELEGRAM_CHANNEL_ID}")
        log.info(f"  GOOGLE_CREDENTIALS_JSON = {self.GOOGLE_CREDENTIALS_JSON_PATH}")
        log.info(f"  GOOGLE_SHEET_ID         = {self.GOOGLE_SHEET_ID}")
        log.info(f"  GOOGLE_SHEET_NAME       = {self.GOOGLE_SHEET_NAME}")
        log.info(f"  GOOGLE_SHEET_LINK_COL   = {self.GOOGLE_SHEET_LINK_COLUMN}")


# Create the single config instance — importing this module triggers validation
config = Config()
