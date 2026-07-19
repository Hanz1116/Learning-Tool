import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("LEARNING_TOOL_DATA_DIR", REPO_ROOT / "data"))
NOTES_DIR = DATA_DIR / "notes"
DB_PATH = DATA_DIR / "learning.db"

MODEL = os.environ.get("LEARNING_TOOL_MODEL", "claude-sonnet-5")

# Expanding review intervals in days. After a good score the video advances to
# the next interval; a poor score resets it to the first one.
REVIEW_INTERVALS = [1, 3, 7, 30, 90]
ADVANCE_THRESHOLD = 80  # score % at or above which the interval advances
RESET_THRESHOLD = 50    # score % below which the interval resets


def ensure_dirs() -> None:
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
