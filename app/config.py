import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent

VISION_MODEL = os.getenv("VISION_MODEL") or "google-gla:gemini-3.5-flash"
AGENT_MODEL = os.getenv("AGENT_MODEL") or "anthropic:claude-sonnet-5-5"
RECIPE_MODEL = os.getenv("RECIPE_MODEL") or AGENT_MODEL
DB_PATH = Path(os.getenv("DB_PATH") or "data/app.db")
if not DB_PATH.is_absolute():
    DB_PATH = ROOT / DB_PATH
UNCERTAIN_THRESHOLD = float(os.getenv("UNCERTAIN_THRESHOLD") or 0.6)
LOG_LEVEL = os.getenv("LOG_LEVEL") or "INFO"
LOGFIRE_TOKEN = os.getenv("LOGFIRE_TOKEN") or None

DATA_DIR = ROOT / "data"
STAPLES_PATH = DATA_DIR / "staples.json"
SYNONYMS_PATH = DATA_DIR / "synonyms.json"
