import json
import logging
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Body
from pydantic import BaseModel

from backend.config import config
from backend.services.kite_client import kite_service, INDEX_CONFIG
from backend.services.analytics import process_option_chain_snapshot
from backend.services.history_buffer import history_buffer
from backend.services.momentum_engine import MomentumEngine
from backend.services.notifier import notifier

router = APIRouter()
logger = logging.getLogger("api")

momentum_engine = MomentumEngine(history_buffer)

# Connected WebSocket clients
active_websockets: List[WebSocket] = []

class TokenExchangeRequest(BaseModel):
    request_token: str

class SymbolSelectRequest(BaseModel):
    symbol: str
    expiry: Optional[str] = None

class ConfigUpdateRequest(BaseModel):
    symbol: Optional[str] = None
    poll_interval_seconds: Optional[int] = None
    history_buffer_size: Optional[int] = None
    atm_band_width: Optional[int] = None
    rules: Optional[Dict[str, Any]] = None
    notifications: Optional[Dict[str, Any]] = None
    mock_mode: Optional[bool] = None
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None

class TestSignalRequest(BaseModel):
    rule_type: Optional[str] = "OI_SURGE"
    strike: Optional[float] = None

@router.get("/status")
def get_status():
    current_symbol = config.data.get("symbol", "NIFTY")
    return {
        "authenticated": kite_service.is_authenticated(),
        "mock_mode": config.mock_mode,
        "current_symbol": current_symbol,
        "poll_interval_seconds": config.data.get("poll_interval_seconds", 1),
        "history_count": len(history_buffer.snapshots),
        "total_signals": len(momentum_engine.signal_log),
        "has_telegram": bool(config.telegram_bot_token and config.telegram_chat_id),
        "connected_clients": len(active_websockets)
    }

@router.get("/auth/login-url")
@router.post("/auth/login-url")
def get_login_url():
    url = kite_service.get_login_url()
    return {"login_url": url}

@router.post("/auth/exchange")
def exchange_token(req: TokenExchangeRequest):
    if not req.request_token:
        raise HTTPException(status_code=400, detail="request_token is required")
    try:
        res = kite_service.exchange_token(req.request_token)
        return res
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/symbols")
def get_symbols():
    return {
        "symbols": kite_service.get_available_symbols(),
        "current_symbol": config.data.get("symbol", "NIFTY")
    }

@router.post("/symbol/select")
def select_symbol(req: SymbolSelectRequest):
    if req.symbol not in INDEX_CONFIG:
        raise HTTPException(status_code=400, detail=f"Unknown symbol {req.symbol}")
    
    config.update({"symbol": req.symbol})
    history_buffer.clear()
    return {"status": "success", "symbol": req.symbol}

@router.get("/option-chain")
def get_option_chain():
    latest = history_buffer.get_latest()
    if latest:
        return latest
    
    # If no snapshot in history yet, compute immediately
    sym = config.data.get("symbol", "NIFTY")
    spot, raw_strikes = kite_service.fetch_option_chain_data(sym)
    snapshot = process_option_chain_snapshot(
        spot, raw_strikes,
        atm_band_width=config.data.get("atm_band_width", 3)
    )
    history_buffer.add_snapshot(snapshot)
    return history_buffer.get_latest()

@router.get("/history")
def get_history():
    return {
        "history": history_buffer.get_pcr_history(),
        "snapshots_count": len(history_buffer.snapshots)
    }

@router.get("/signals")
def get_signals():
    return {
        "signals": momentum_engine.get_signal_log()
    }

@router.get("/config")
def get_config():
    return {
        "config": config.data,
        "mock_mode": config.mock_mode,
        "kite_api_key_set": bool(config.kite_api_key),
        "kite_authenticated": kite_service.is_authenticated(),
        "telegram_configured": bool(config.telegram_bot_token and config.telegram_chat_id)
    }

@router.post("/config")
def update_config(req: ConfigUpdateRequest):
    updates = {}
    if req.symbol is not None:
        updates["symbol"] = req.symbol
    if req.poll_interval_seconds is not None:
        updates["poll_interval_seconds"] = max(1, min(120, req.poll_interval_seconds))
    if req.history_buffer_size is not None:
        updates["history_buffer_size"] = max(10, min(300, req.history_buffer_size))
        history_buffer.max_size = updates["history_buffer_size"]
    if req.atm_band_width is not None:
        updates["atm_band_width"] = max(1, min(10, req.atm_band_width))
    if req.rules is not None:
        updates["rules"] = req.rules
    if req.notifications is not None:
        updates["notifications"] = req.notifications

    if updates:
        config.update(updates)

    if req.mock_mode is not None:
        config.update_env("MOCK_MODE", "true" if req.mock_mode else "false")
    if req.telegram_bot_token is not None:
        config.update_env("TELEGRAM_BOT_TOKEN", req.telegram_bot_token)
    if req.telegram_chat_id is not None:
        config.update_env("TELEGRAM_CHAT_ID", req.telegram_chat_id)

    return {"status": "success", "config": config.data, "mock_mode": config.mock_mode}

@router.post("/simulate-signal")
async def simulate_signal(req: TestSignalRequest):
    """Triggers a test signal to verify all four notification channels."""
    sym = config.data.get("symbol", "NIFTY")
    latest = history_buffer.get_latest()
    strike = req.strike or (latest.get("atm_strike", 24500.0) if latest else 24500.0)
    
    test_sig = momentum_engine.create_simulated_signal(
        rule_type=req.rule_type or "OI_SURGE",
        strike=strike
    )

    # Trigger Telegram channel
    notifier.send_telegram_alert(test_sig, sym)

    # Broadcast to connected WebSockets for On-Screen, Audio, and Browser Push
    await broadcast_event({
        "type": "NEW_SIGNALS",
        "signals": [test_sig]
    })

    return {"status": "success", "signal": test_sig}

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_websockets.append(websocket)
    logger.info(f"WebSocket client connected. Total: {len(active_websockets)}")
    try:
        # Send initial snapshot if available
        latest = history_buffer.get_latest()
        if latest:
            await websocket.send_json({
                "type": "SNAPSHOT",
                "data": latest,
                "history": history_buffer.get_pcr_history(),
                "signals": momentum_engine.get_signal_log()
            })

        while True:
            # Keep connection alive, listen for ping/client messages
            msg = await websocket.receive_text()
            try:
                data = json.loads(msg)
                if data.get("action") == "PING":
                    await websocket.send_json({"type": "PONG"})
            except Exception:
                pass
    except WebSocketDisconnect:
        if websocket in active_websockets:
            active_websockets.remove(websocket)
        logger.info(f"WebSocket client disconnected. Total: {len(active_websockets)}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        if websocket in active_websockets:
            active_websockets.remove(websocket)

async def broadcast_event(event_data: Dict[str, Any]):
    """Broadcast an event payload to all connected clients."""
    disconnected = []
    for ws in active_websockets:
        try:
            await ws.send_json(event_data)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        if ws in active_websockets:
            active_websockets.remove(ws)
