"""
logger.py — Shared colorama-based logger for the Telegram pipeline.

Provides a get_logger(module_name) function that returns a Logger instance
with color-coded methods: info, success, warning, error, debug, section.

Every log line includes: [TIMESTAMP] [LEVEL] [module_name] message

Imports: colorama
Exports: get_logger()
"""

from datetime import datetime
from colorama import init, Fore, Style

# Initialize colorama so colors auto-reset after each print
init(autoreset=True)


class Logger:
    """Color-coded console logger with level-specific formatting."""

    def __init__(self, module_name):
        # Store the module name so every log line identifies where it came from
        self.module_name = module_name

    def _timestamp(self):
        """Return the current time formatted for log output."""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _format(self, level, color, message):
        """Build and print a formatted log line with color."""
        timestamp = self._timestamp()
        print(f"{color}[{timestamp}] [{level}] [{self.module_name}] {message}{Style.RESET_ALL}")

    def info(self, message):
        """Log an informational message in CYAN."""
        self._format("INFO", Fore.CYAN, message)

    def success(self, message):
        """Log a success message in GREEN."""
        self._format("SUCCESS", Fore.GREEN, message)

    def warning(self, message):
        """Log a warning message in YELLOW."""
        self._format("WARNING", Fore.YELLOW, message)

    def error(self, message):
        """Log an error message in RED."""
        self._format("ERROR", Fore.RED, message)

    def debug(self, message):
        """Log a debug message in MAGENTA."""
        self._format("DEBUG", Fore.MAGENTA, message)

    def section(self, message):
        """Log a section header in bold BLUE with separator lines."""
        timestamp = self._timestamp()
        separator = "=" * 60
        print(f"{Fore.BLUE}{Style.BRIGHT}{separator}")
        print(f"[{timestamp}] [{self.module_name}] {message}")
        print(f"{separator}{Style.RESET_ALL}")


def get_logger(module_name):
    """Create and return a Logger instance for the given module name."""
    return Logger(module_name)
