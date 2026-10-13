import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY") or None
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL") or "https://api.deepseek.com"
QWEN_API_KEY = os.getenv("QWEN_API_KEY") or None

VISION_MODEL = os.getenv("VISION_MODEL") or "deepseek-flash"
AGENT_MODEL = os.getenv("AGENT_MODEL") or "deepseek-v4-pro"
RECIPE_MODEL = os.getenv("RECIPE_MODEL") or "deepseek-flash"
VISION_TILES = int(os.getenv("VISION_TILES") or 1)
# DeepSeek V4 models think by default; thinking roughly doubles latency. "on" / "off".
AGENT_THINKING = (os.getenv("AGENT_THINKING") or "off").lower() == "on"
RECIPE_THINKING = (os.getenv("RECIPE_THINKING") or "off").lower() == "on"
DB_PATH = Path(os.getenv("DB_PATH") or "data/app.db")
if not DB_PATH.is_absolute():
    DB_PATH = ROOT / DB_PATH
UNCERTAIN_THRESHOLD = float(os.getenv("UNCERTAIN_THRESHOLD") or 0.6)
LOG_LEVEL = os.getenv("LOG_LEVEL") or "INFO"
LOGFIRE_TOKEN = os.getenv("LOGFIRE_TOKEN") or None

DATA_DIR = ROOT / "data"
STAPLES_PATH = DATA_DIR / "staples.json"
SYNONYMS_PATH = DATA_DIR / "synonyms.json"
DEMO_SEED_PATH = DATA_DIR / "demo_seed.json"
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR") or DATA_DIR / "uploads")  # photos sent to /chat
