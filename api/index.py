import os
import sys
from pathlib import Path

# Add search paths for backend imports
api_dir = Path(__file__).resolve().parent
root_dir = api_dir.parent

for p in [str(api_dir), str(root_dir), str(api_dir / "backend"), str(root_dir / "backend")]:
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from backend.app import app
except Exception:
    from api.backend.app import app

try:
    from mangum import Mangum
    handler = Mangum(app, lifespan="off")
except Exception:
    handler = app

application = app
