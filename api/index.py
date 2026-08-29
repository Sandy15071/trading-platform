import os
import sys
from pathlib import Path

# Add current api directory and root directory to sys.path
api_dir = Path(__file__).resolve().parent
root_dir = api_dir.parent

for p in [str(api_dir), str(root_dir)]:
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from backend.app import app
except Exception:
    from api.backend.app import app

# Export ASGI application instances
handler = app
application = app
