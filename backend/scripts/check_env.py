"""Print ONLY whether the required env vars are set. Never prints any value."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import load_env  # noqa: E402

load_env()
print(f"OPENAI_API_KEY set: {bool(os.getenv('OPENAI_API_KEY', '').strip())}")
print(f"REALTIME_MODEL set: {bool(os.getenv('REALTIME_MODEL', '').strip())}")
