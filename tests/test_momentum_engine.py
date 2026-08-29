import pytest
from backend.services.history_buffer import HistoryBuffer
from backend.services.momentum_engine import MomentumEngine

@pytest.fixture
def engine():
    buf = HistoryBuffer(max_size=30)
    eng = MomentumEngine(buf)
    return eng

def test_rule_1_oi_surge(engine):
    rules_cfg = {"oi_surge_pct": 8.0}
    snapshot = {
        "spot_price": 24500.0,
        "atm_strike": 24500.0,
        "max_pain": 24500.0,
        "pcr": {"total_pcr": 1.0, "near_atm_pcr": 1.0},
        "strikes": [
            {
                "strike": 24600.0,
                "ce_oi": 55000,
                "ce_delta_oi": 5000,
                "ce_delta_oi_pct": 10.0, # > 8.0%
                "pe_oi": 20000,
                "pe_delta_oi": 0,
                "pe_delta_oi_pct": 0.0
            }
        ]
    }
    signals = engine.evaluate_rules(snapshot, rules_cfg)
    assert len(signals) == 1
    assert signals[0]["rule_type"] == "OI_SURGE"
    assert signals[0]["strike"] == 24600.0
    assert signals[0]["side"] == "CE"
    assert "Build-up" in signals[0]["direction"]

def test_rule_2_pcr_cross(engine):
    rules_cfg = {
        "pcr_bullish_threshold": 1.2,
        "pcr_bearish_threshold": 0.8,
        "pcr_delta_threshold": 0.15
    }
    
    # Cycle 1: PCR at 1.15
    snap1 = {
        "spot_price": 24500.0,
        "atm_strike": 24500.0,
        "max_pain": 24500.0,
        "pcr": {"total_pcr": 1.15, "near_atm_pcr": 1.15},
        "strikes": []
    }
    engine.history.add_snapshot(snap1)

    # Cycle 2: PCR crosses to 1.35 (> 1.2)
    snap2 = {
        "spot_price": 24500.0,
        "atm_strike": 24500.0,
        "max_pain": 24500.0,
        "pcr": {"total_pcr": 1.35, "near_atm_pcr": 1.35},
        "strikes": []
    }
    signals = engine.evaluate_rules(snap2, rules_cfg)
    
    rule_types = [s["rule_type"] for s in signals]
    assert "PCR_CROSS" in rule_types

def test_rule_3_max_pain_drift(engine):
    rules_cfg = {"max_pain_drift_enabled": True}
    
    # Previous snapshot: Max pain at 24400
    snap1 = {
        "spot_price": 24500.0,
        "atm_strike": 24500.0,
        "max_pain": 24400.0,
        "pcr": {"total_pcr": 1.0},
        "strikes": []
    }
    engine.history.add_snapshot(snap1)

    # Current snapshot: Max pain drifts to 24500 (towards spot)
    snap2 = {
        "spot_price": 24500.0,
        "atm_strike": 24500.0,
        "max_pain": 24500.0,
        "pcr": {"total_pcr": 1.0},
        "strikes": []
    }
    signals = engine.evaluate_rules(snap2, rules_cfg)
    assert any(s["rule_type"] == "MAX_PAIN_DRIFT" for s in signals)

def test_rule_4_iv_spike(engine):
    rules_cfg = {"iv_spike_pct": 15.0}

    # Add historical cycles with normal IV ~ 15.0%
    for _ in range(5):
        engine.history.add_snapshot({
            "spot_price": 24500.0,
            "strikes": [{"strike": 24500.0, "ce_iv": 15.0, "pe_iv": 15.0}]
        })

    # Current cycle: IV jumps to 22.0% (> 15% jump vs 15.0 baseline)
    curr_snap = {
        "spot_price": 24500.0,
        "atm_strike": 24500.0,
        "max_pain": 24500.0,
        "pcr": {"total_pcr": 1.0},
        "strikes": [{"strike": 24500.0, "ce_iv": 22.0, "pe_iv": 15.0}]
    }
    signals = engine.evaluate_rules(curr_snap, rules_cfg)
    assert any(s["rule_type"] == "IV_SPIKE" and s["side"] == "CE" for s in signals)

def test_rule_5_atm_imbalance(engine):
    rules_cfg = {"atm_imbalance_ratio": 1.8}
    snapshot = {
        "spot_price": 24500.0,
        "atm_strike": 24500.0,
        "max_pain": 24500.0,
        "pcr": {"total_pcr": 1.0},
        "strikes": [
            {
                "strike": 24500.0,
                "is_atm": True,
                "ce_oi": 20000,
                "pe_oi": 50000, # 50000 / 20000 = 2.5x (> 1.8)
            }
        ]
    }
    signals = engine.evaluate_rules(snapshot, rules_cfg)
    assert any(s["rule_type"] == "ATM_IMBALANCE" and s["side"] == "PE" for s in signals)
