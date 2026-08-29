import sys
import os
import traceback
from pathlib import Path

current_dir = Path(__file__).resolve().parent
root_dir = current_dir.parent

for p in [str(current_dir), str(root_dir), str(current_dir / "backend"), str(root_dir / "backend")]:
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from backend.app import app
except Exception as e:
    err_tb = traceback.format_exc()
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    app = FastAPI(title="Diagnostic Fallback")
    
    @app.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"])
    def catch_all(full_path: str):
        return JSONResponse(status_code=500, content={"error": str(e), "traceback": err_tb})

handler = app
