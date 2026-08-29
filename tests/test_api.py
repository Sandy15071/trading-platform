import pytest
from fastapi.testclient import TestClient
from backend.app import app

client = TestClient(app)

def test_api_status():
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert "mock_mode" in data
    assert "current_symbol" in data
    assert "poll_interval_seconds" in data

def test_api_symbols():
    response = client.get("/api/symbols")
    assert response.status_code == 200
    data = response.json()
    symbols = [s["symbol"] for s in data["symbols"]]
    assert "NIFTY" in symbols
    assert "BANKNIFTY" in symbols

def test_api_option_chain():
    response = client.get("/api/option-chain")
    assert response.status_code == 200
    data = response.json()
    assert "spot_price" in data
    assert "atm_strike" in data
    assert "strikes" in data
    assert len(data["strikes"]) == 21
    assert "max_pain" in data
    assert "pcr" in data

def test_api_history():
    response = client.get("/api/history")
    assert response.status_code == 200
    data = response.json()
    assert "history" in data

def test_api_config_get_and_update():
    get_res = client.get("/api/config")
    assert get_res.status_code == 200
    
    post_res = client.post("/api/config", json={
        "poll_interval_seconds": 2,
        "rules": {"oi_surge_pct": 9.5}
    })
    assert post_res.status_code == 200
    updated_data = post_res.json()
    assert updated_data["config"]["poll_interval_seconds"] == 2
    assert updated_data["config"]["rules"]["oi_surge_pct"] == 9.5

    # Restore to 1 second
    client.post("/api/config", json={"poll_interval_seconds": 1, "rules": {"oi_surge_pct": 8.0}})

def test_api_simulate_signal():
    res = client.post("/api/simulate-signal", json={
        "rule_type": "OI_SURGE",
        "strike": 24500.0
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["signal"]["rule_type"] == "OI_SURGE"
