"""Vercel entrypoint for the combined ApplyLens web application and API."""

import os
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parent
API_ROOT = REPOSITORY_ROOT / "apps" / "api"
WEB_BUILD = REPOSITORY_ROOT / "apps" / "web" / "dist"

os.environ.setdefault("WEB_STATIC_DIR", str(WEB_BUILD))
sys.path.insert(0, str(API_ROOT))

from app.main import app  # noqa: E402
