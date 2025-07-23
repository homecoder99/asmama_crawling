"""Configuration settings for the Asmama crawler."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"

# Create directories if they don't exist
DATA_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# Crawler settings
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_DELAY = 5

# Storage settings
EXCEL_OUTPUT_PATH = DATA_DIR / "asmama_products.xlsx"
DB_CONNECTION_STRING = os.getenv("DATABASE_URL", "postgresql://localhost/asmama")

# Logging settings
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# Asmama specific settings
ASMAMA_BASE_URL = "https://www.asmama.com"
ASMAMA_CATEGORIES = [
    "electronics",
    "fashion",
    "home",
    "beauty",
    "sports"
]