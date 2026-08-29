import os
import time
import asyncio
import logging
from typing import Optional, Dict, Any
from urllib.parse import quote
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse

from backend.config import config
from backend.services.kite_client import kite_service
from backend.services.analytics import process_option_chain_snapshot
from backend.services.history_buffer import history_buffer
from backend.services.notifier import notifier
from backend.routes.api import router as api_router, momentum_engine, broadcast_event

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("server")

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

poll_task = None
is_running = True

last_buildup_eval_time = 0.0
latched_buildups: Dict[float, Dict[str, str]] = {}

async def polling_worker():
    """Background worker polling option chain data at configured cadence."""
    global is_running, last_buildup_eval_time, latched_buildups
    logger.info("Background option-chain polling worker started.")
    
    while is_running:
        try:
            interval = int(config.data.get("poll_interval_seconds", 1))
            symbol = config.data.get("symbol", "NIFTY")
            atm_band = int(config.data.get("atm_band_width", 3))
            rules_cfg = config.data.get("rules", {})

            # 1. Fetch Option Chain Data
            prev_snapshot = history_buffer.get_latest()
            now = time.time()
            spot, raw_strikes = kite_service.fetch_option_chain_data(symbol)

            # Re-evaluate 15-second build-up latch once every 15 seconds
            should_update_buildup = (now - last_buildup_eval_time) >= 15.0 or not latched_buildups
            if should_update_buildup:
                ref_15s_snap = history_buffer.get_snapshot_seconds_ago(15.0) or prev_snapshot
                temp_snap = process_option_chain_snapshot(
                    spot_price=spot,
                    current_raw_strikes=raw_strikes,
                    prev_snapshot=prev_snapshot,
                    session_open_snapshot=history_buffer.session_open_snapshot,
                    atm_band_width=atm_band,
                    buildup_ref_snapshot=ref_15s_snap
                )
                latched_buildups = {
                    st["strike"]: {
                        "ce_buildup": st["ce_buildup"],
                        "pe_buildup": st["pe_buildup"]
                    }
                    for st in temp_snap["strikes"]
                }
                last_buildup_eval_time = now

            # 2. Compute Official Snapshot with the 15-second Latched Build-up States
            snapshot = process_option_chain_snapshot(
                spot_price=spot,
                current_raw_strikes=raw_strikes,
                prev_snapshot=prev_snapshot,
                session_open_snapshot=history_buffer.session_open_snapshot,
                atm_band_width=atm_band,
                latched_buildup_map=latched_buildups
            )

            # 3. Append to In-Memory Rolling History Buffer
            history_buffer.add_snapshot(snapshot)

            # 4. Evaluate Momentum Rules
            new_signals = momentum_engine.evaluate_rules(snapshot, rules_cfg)

            # 5. Dispatch Telegram Notifications
            if new_signals:
                notifier.dispatch_signals(new_signals, symbol)

            # 6. Broadcast Real-Time Update over WebSocket
            await broadcast_event({
                "type": "CYCLE_UPDATE",
                "symbol": symbol,
                "data": snapshot,
                "history": history_buffer.get_pcr_history(),
                "new_signals": new_signals,
                "all_signals": momentum_engine.get_signal_log(),
                "poll_interval_seconds": interval
            })

        except Exception as e:
            logger.error(f"Error in polling cycle: {e}", exc_info=True)

        # Sleep for poll interval or 1s default
        await asyncio.sleep(config.data.get("poll_interval_seconds", 1))

@asynccontextmanager
async def lifespan(app: FastAPI):
    global poll_task, is_running
    is_serverless = bool(os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"))
    if not is_serverless:
        is_running = True
        poll_task = asyncio.create_task(polling_worker())
    yield
    if not is_serverless:
        is_running = False
        if poll_task:
            poll_task.cancel()
            try:
                await poll_task
            except asyncio.CancelledError:
                pass
        logger.info("Background polling worker stopped.")

app = FastAPI(
    title="Option Chain Momentum Indicator",
    description="Zerodha Kite Connect Option Chain Momentum Indicator & Alert Dashboard",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routes with /api prefix and bare prefix for seamless serverless routing
app.include_router(api_router, prefix="/api")
app.include_router(api_router)

from fastapi.responses import HTMLResponse, RedirectResponse, Response, JSONResponse

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Unhandled Exception on {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": str(exc), "type": type(exc).__name__}
    )

handler = app

# Direct static file serving route for serverless environments
@app.get("/static/{file_path:path}")
async def serve_static(file_path: str):
    target = FRONTEND_DIR / file_path
    if target.exists() and target.is_file():
        media_type = "text/plain"
        if file_path.endswith(".css"):
            media_type = "text/css; charset=utf-8"
        elif file_path.endswith(".js"):
            media_type = "application/javascript; charset=utf-8"
        elif file_path.endswith(".html"):
            media_type = "text/html; charset=utf-8"
        elif file_path.endswith(".json"):
            media_type = "application/json"
        elif file_path.endswith(".png"):
            media_type = "image/png"
        elif file_path.endswith(".svg"):
            media_type = "image/svg+xml"
            
        try:
            with open(target, "rb") as f:
                return Response(content=f.read(), media_type=media_type)
        except Exception:
            pass
    return Response(content="File not found", status_code=404)

@app.get("/")
@app.get("/callback")
@app.get("/api/auth/callback")
@app.get("/redirect")
@app.get("/login/callback")
@app.get("/auth/callback")
async def handle_callback_or_index(
    request_token: Optional[str] = None,
    status: Optional[str] = None,
    action: Optional[str] = None
):
    """
    Handles both frontend index serving and automatic Zerodha Kite Connect login redirects.
    If request_token is present in URL, automatically exchanges it for access_token and saves to .env.
    """
    if request_token:
        try:
            logger.info(f"Received request_token from Kite redirect: {request_token[:6]}...")
            res = kite_service.exchange_token(request_token)
            token = res.get("access_token", "")
            return RedirectResponse(url=f"/?auth=success&access_token={token}")
        except Exception as e:
            logger.error(f"Failed to auto-exchange request_token: {e}")
            return RedirectResponse(url=f"/?auth=error&msg={quote(str(e))}")

    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        try:
            with open(index_file, "r", encoding="utf-8") as f:
                return HTMLResponse(content=f.read())
        except Exception as e:
            logger.error(f"Error reading index.html: {e}")
    return HTMLResponse(content="<h1>Option Chain Momentum Indicator</h1><p>Frontend loading...</p>")
