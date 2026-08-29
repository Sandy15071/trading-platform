import pytest
from backend.services.analytics import (
    get_atm_strike,
    select_atm_range,
    calculate_max_pain,
    calculate_pcr,
    calculate_iv_skew,
    process_option_chain_snapshot
)

def test_atm_strike_resolution():
    strikes = [24300, 24350, 24400, 24450, 24500, 24550, 24600]
    assert get_atm_strike(24480, strikes) == 24500
    assert get_atm_strike(24420, strikes) == 24400
    assert get_atm_strike(24450, strikes) == 24450

def test_select_atm_range_21_strikes():
    available = [24000 + i * 50 for i in range(30)] # 30 strikes
    spot = 24520 # ATM is 24500 (index 10)
    atm, selected = select_atm_range(spot, available, range_count=10)
    
    assert atm == 24500
    assert len(selected) == 21
    assert selected[0] == 24000
    assert selected[-1] == 25000
    assert selected[10] == 24500

def test_calculate_pcr():
    data = [
        {"strike": 24400, "ce_oi": 10000, "pe_oi": 20000},
        {"strike": 24500, "ce_oi": 20000, "pe_oi": 15000}, # ATM
        {"strike": 24600, "ce_oi": 30000, "pe_oi": 10000},
    ]
    # Total CE = 60,000, Total PE = 45,000 -> PCR = 45000 / 60000 = 0.75
    pcr = calculate_pcr(data, atm_strike=24500, atm_band_width=1)
    assert pcr["total_ce_oi"] == 60000
    assert pcr["total_pe_oi"] == 45000
    assert pcr["total_pcr"] == 0.75
    assert pcr["near_atm_pcr"] == 0.75

def test_calculate_max_pain_known_scenario():
    # Setup option chain where minimum loss clearly occurs at strike 24500
    data = [
        {"strike": 24400, "ce_oi": 1000, "pe_oi": 50000}, # Heavy put OI at 24400
        {"strike": 24500, "ce_oi": 10000, "pe_oi": 10000}, # Equal at 24500
        {"strike": 24600, "ce_oi": 50000, "pe_oi": 1000}, # Heavy call OI at 24600
    ]
    res = calculate_max_pain(data)
    # Expiry at 24500 causes max loss to option buyers (min payout to writers)
    assert res["max_pain_strike"] == 24500.0

def test_process_option_chain_snapshot_deltas():
    raw_current = [
        {"strike": 24000 + i * 50, "ce_oi": 10000 + i * 100, "pe_oi": 12000, "ce_ltp": 150.0, "pe_ltp": 80.0, "ce_iv": 14.0, "pe_iv": 15.0}
        for i in range(25)
    ]
    prev_snapshot = {
        "strikes": [
            {"strike": 24500, "ce_oi": 8000, "pe_oi": 12000, "ce_iv": 14.0, "pe_iv": 15.0}
        ]
    }
    
    snapshot = process_option_chain_snapshot(24520, raw_current, prev_snapshot=prev_snapshot)
    assert snapshot["atm_strike"] == 24500
    assert snapshot["strike_count"] == 21
    
    # Check delta for strike 24500
    atm_row = [s for s in snapshot["strikes"] if s["strike"] == 24500][0]
    # Current CE OI for 24500 is 10000 + 10*100 = 11000. Prev was 8000.
    assert atm_row["ce_delta_oi"] == 3000
    assert atm_row["ce_delta_oi_pct"] == 37.5 # (3000 / 8000) * 100
