from typing import List, Dict, Any, Optional, Tuple

def get_atm_strike(spot_price: float, available_strikes: List[float]) -> float:
    """Find the strike closest to the current spot price."""
    if not available_strikes:
        return spot_price
    return min(available_strikes, key=lambda strike: abs(strike - spot_price))

def select_atm_range(
    spot_price: float,
    available_strikes: List[float],
    range_count: int = 10
) -> Tuple[float, List[float]]:
    """
    Selects ATM ± range_count strikes (e.g. 10 ITM + 1 ATM + 10 OTM = 21 strikes).
    Returns (atm_strike, selected_strikes_sorted).
    """
    sorted_strikes = sorted(list(set(available_strikes)))
    if not sorted_strikes:
        return spot_price, []

    atm_strike = get_atm_strike(spot_price, sorted_strikes)
    atm_idx = sorted_strikes.index(atm_strike)

    start_idx = max(0, atm_idx - range_count)
    end_idx = min(len(sorted_strikes), atm_idx + range_count + 1)

    # Ensure symmetric window if possible
    selected_strikes = sorted_strikes[start_idx:end_idx]
    return atm_strike, selected_strikes

def calculate_max_pain(strikes_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Computes Max Pain strike across the given strike list with Call and Put OI.
    Formula:
    For candidate strike S:
      Loss(S) = sum_over_all_K [ CE_OI(K) * max(0, S - K) + PE_OI(K) * max(0, K - S) ]
    Max Pain is the strike S that minimizes Total Loss.
    """
    if not strikes_data:
        return {"max_pain_strike": 0.0, "min_loss": 0.0, "payouts": {}}

    payouts: Dict[float, float] = {}
    candidate_strikes = [item["strike"] for item in strikes_data]

    for s in candidate_strikes:
        total_payout = 0.0
        for item in strikes_data:
            k = item["strike"]
            ce_oi = item.get("ce_oi", 0) or 0
            pe_oi = item.get("pe_oi", 0) or 0
            
            # Call loss if underlying expires at s
            ce_loss = ce_oi * max(0.0, s - k)
            # Put loss if underlying expires at s
            pe_loss = pe_oi * max(0.0, k - s)
            
            total_payout += (ce_loss + pe_loss)
        payouts[s] = total_payout

    min_strike = min(payouts.keys(), key=lambda k: payouts[k])
    return {
        "max_pain_strike": float(min_strike),
        "min_loss": float(payouts[min_strike]),
        "payouts": payouts
    }

def calculate_pcr(
    strikes_data: List[Dict[str, Any]],
    atm_strike: float,
    atm_band_width: int = 3
) -> Dict[str, float]:
    """
    Calculates:
    1. Total PCR across all fetched strikes: sum(PE OI) / sum(CE OI)
    2. Near-ATM PCR within ATM ± atm_band_width strikes.
    """
    total_ce_oi = 0.0
    total_pe_oi = 0.0
    near_ce_oi = 0.0
    near_pe_oi = 0.0

    sorted_strikes = sorted([item["strike"] for item in strikes_data])
    if atm_strike in sorted_strikes:
        atm_idx = sorted_strikes.index(atm_strike)
        near_min_idx = max(0, atm_idx - atm_band_width)
        near_max_idx = min(len(sorted_strikes) - 1, atm_idx + atm_band_width)
        near_strike_set = set(sorted_strikes[near_min_idx:near_max_idx + 1])
    else:
        near_strike_set = set()

    for item in strikes_data:
        ce_oi = float(item.get("ce_oi", 0) or 0)
        pe_oi = float(item.get("pe_oi", 0) or 0)
        total_ce_oi += ce_oi
        total_pe_oi += pe_oi

        if item["strike"] in near_strike_set:
            near_ce_oi += ce_oi
            near_pe_oi += pe_oi

    total_pcr = round(total_pe_oi / total_ce_oi, 3) if total_ce_oi > 0 else 1.0
    near_atm_pcr = round(near_pe_oi / near_ce_oi, 3) if near_ce_oi > 0 else 1.0

    return {
        "total_ce_oi": total_ce_oi,
        "total_pe_oi": total_pe_oi,
        "total_pcr": total_pcr,
        "near_ce_oi": near_ce_oi,
        "near_pe_oi": near_pe_oi,
        "near_atm_pcr": near_atm_pcr
    }

def calculate_iv_skew(
    strikes_data: List[Dict[str, Any]],
    spot_price: float,
    atm_strike: float
) -> Dict[str, Any]:
    """
    Computes IV skew details across the strike range.
    Compares OTM Put IV vs OTM Call IV to indicate downside vs upside premium pricing.
    """
    otm_put_ivs = []
    otm_call_ivs = []
    skew_curve = []

    for item in strikes_data:
        strike = item["strike"]
        ce_iv = item.get("ce_iv", 0.0) or 0.0
        pe_iv = item.get("pe_iv", 0.0) or 0.0

        if strike < spot_price:
            # OTM Put
            if pe_iv > 0:
                otm_put_ivs.append(pe_iv)
        elif strike > spot_price:
            # OTM Call
            if ce_iv > 0:
                otm_call_ivs.append(ce_iv)

        skew_curve.append({
            "strike": strike,
            "ce_iv": round(ce_iv, 2),
            "pe_iv": round(pe_iv, 2),
            "blended_iv": round((ce_iv + pe_iv) / 2 if (ce_iv > 0 and pe_iv > 0) else (ce_iv or pe_iv), 2)
        })

    avg_otm_put_iv = sum(otm_put_ivs) / len(otm_put_ivs) if otm_put_ivs else 0.0
    avg_otm_call_iv = sum(otm_call_ivs) / len(otm_call_ivs) if otm_call_ivs else 0.0
    skew_difference = round(avg_otm_put_iv - avg_otm_call_iv, 2)

    return {
        "avg_otm_put_iv": round(avg_otm_put_iv, 2),
        "avg_otm_call_iv": round(avg_otm_call_iv, 2),
        "skew_difference": skew_difference,
        "skew_bias": "PUT_PREMIUM_HIGH" if skew_difference > 1.0 else ("CALL_PREMIUM_HIGH" if skew_difference < -1.0 else "BALANCED"),
        "curve": skew_curve
    }

def determine_buildup(delta_oi: int | float, delta_ltp: float) -> str:
    """
    Derives derivative build-up state from Price & OI movement:
    - LONG_BUILDUP (Price >= 0, OI > 0)
    - SHORT_BUILDUP (Price < 0, OI > 0)
    - SHORT_COVERING (Price >= 0, OI < 0)
    - LONG_UNWINDING (Price < 0, OI < 0)
    """
    if delta_oi > 0:
        return "LONG_BUILDUP" if delta_ltp >= 0 else "SHORT_BUILDUP"
    elif delta_oi < 0:
        return "SHORT_COVERING" if delta_ltp >= 0 else "LONG_UNWINDING"
    return "NEUTRAL"

def process_option_chain_snapshot(
    spot_price: float,
    current_raw_strikes: List[Dict[str, Any]],
    prev_snapshot: Optional[Dict[str, Any]] = None,
    session_open_snapshot: Optional[Dict[str, Any]] = None,
    atm_band_width: int = 3,
    buildup_ref_snapshot: Optional[Dict[str, Any]] = None,
    latched_buildup_map: Optional[Dict[float, Dict[str, str]]] = None
) -> Dict[str, Any]:
    """
    Takes raw strike data (strike, CE/PE LTP, OI, IV), computes delta OI vs previous cycle,
    PCR, Max Pain, IV Skew, and structures the complete cycle payload with 15-second build-up states.
    """
    prev_oi_map = {}
    if prev_snapshot and "strikes" in prev_snapshot:
        for st in prev_snapshot["strikes"]:
            prev_oi_map[st["strike"]] = {
                "ce_oi": st.get("ce_oi", 0),
                "pe_oi": st.get("pe_oi", 0),
                "ce_ltp": st.get("ce_ltp", 0.0),
                "pe_ltp": st.get("pe_ltp", 0.0),
                "ce_iv": st.get("ce_iv", 0.0),
                "pe_iv": st.get("pe_iv", 0.0),
            }

    buildup_ref_map = {}
    ref_snap = buildup_ref_snapshot or prev_snapshot
    if ref_snap and "strikes" in ref_snap:
        for st in ref_snap["strikes"]:
            buildup_ref_map[st["strike"]] = {
                "ce_oi": st.get("ce_oi", 0),
                "pe_oi": st.get("pe_oi", 0),
                "ce_ltp": st.get("ce_ltp", 0.0),
                "pe_ltp": st.get("pe_ltp", 0.0),
            }

    session_open_map = {}
    if session_open_snapshot and "strikes" in session_open_snapshot:
        for st in session_open_snapshot["strikes"]:
            session_open_map[st["strike"]] = {
                "ce_oi": st.get("ce_oi", 0),
                "pe_oi": st.get("pe_oi", 0),
                "ce_ltp": st.get("ce_ltp", 0.0),
                "pe_ltp": st.get("pe_ltp", 0.0),
            }

    available_strikes = [item["strike"] for item in current_raw_strikes]
    atm_strike, selected_strikes = select_atm_range(spot_price, available_strikes, range_count=10)

    processed_strikes = []
    for item in current_raw_strikes:
        if item["strike"] not in selected_strikes:
            continue

        strike = item["strike"]
        ce_oi = int(item.get("ce_oi", 0) or 0)
        pe_oi = int(item.get("pe_oi", 0) or 0)
        ce_ltp = float(item.get("ce_ltp", 0.0) or 0.0)
        pe_ltp = float(item.get("pe_ltp", 0.0) or 0.0)
        ce_iv = float(item.get("ce_iv", 0.0) or 0.0)
        pe_iv = float(item.get("pe_iv", 0.0) or 0.0)

        # Delta OI & LTP vs prev 1-second cycle
        prev_data = prev_oi_map.get(strike, {})
        prev_ce_oi = prev_data.get("ce_oi", ce_oi)
        prev_pe_oi = prev_data.get("pe_oi", pe_oi)
        prev_ce_ltp = prev_data.get("ce_ltp", ce_ltp)
        prev_pe_ltp = prev_data.get("pe_ltp", pe_ltp)

        delta_ce_oi = ce_oi - prev_ce_oi
        delta_pe_oi = pe_oi - prev_pe_oi
        delta_ce_ltp = round(ce_ltp - prev_ce_ltp, 2)
        delta_pe_ltp = round(pe_ltp - prev_pe_ltp, 2)

        # 15-Second Build-up (LB, SB, SC, LU) state computation
        b_data = buildup_ref_map.get(strike, prev_data)
        b_ce_oi = b_data.get("ce_oi", ce_oi)
        b_pe_oi = b_data.get("pe_oi", pe_oi)
        b_ce_ltp = b_data.get("ce_ltp", ce_ltp)
        b_pe_ltp = b_data.get("pe_ltp", pe_ltp)

        delta_15s_ce_oi = ce_oi - b_ce_oi
        delta_15s_pe_oi = pe_oi - b_pe_oi
        delta_15s_ce_ltp = round(ce_ltp - b_ce_ltp, 2)
        delta_15s_pe_ltp = round(pe_ltp - b_pe_ltp, 2)

        if latched_buildup_map and strike in latched_buildup_map:
            ce_buildup = latched_buildup_map[strike].get("ce_buildup", "NEUTRAL")
            pe_buildup = latched_buildup_map[strike].get("pe_buildup", "NEUTRAL")
        else:
            ce_buildup = determine_buildup(delta_15s_ce_oi, delta_15s_ce_ltp)
            pe_buildup = determine_buildup(delta_15s_pe_oi, delta_15s_pe_ltp)

        ce_15s_pct_change = round((delta_15s_ce_oi / b_ce_oi * 100), 2) if b_ce_oi > 0 else 0.0
        pe_15s_pct_change = round((delta_15s_pe_oi / b_pe_oi * 100), 2) if b_pe_oi > 0 else 0.0

        # Delta OI vs session open
        open_data = session_open_map.get(strike, {})
        open_ce_oi = open_data.get("ce_oi", ce_oi)
        open_pe_oi = open_data.get("pe_oi", pe_oi)
        session_delta_ce_oi = ce_oi - open_ce_oi
        session_delta_pe_oi = pe_oi - open_pe_oi

        # Percentage change (1-second)
        ce_oi_pct_change = round((delta_ce_oi / prev_ce_oi * 100), 2) if prev_ce_oi > 0 else 0.0
        pe_oi_pct_change = round((delta_pe_oi / prev_pe_oi * 100), 2) if prev_pe_oi > 0 else 0.0

        processed_strikes.append({
            "strike": strike,
            "is_atm": (strike == atm_strike),
            "ce_ltp": round(ce_ltp, 2),
            "ce_delta_ltp": delta_ce_ltp,
            "ce_oi": ce_oi,
            "ce_delta_oi": delta_ce_oi,
            "ce_delta_oi_pct": ce_oi_pct_change,
            "ce_delta_oi_15s": delta_15s_ce_oi,
            "ce_delta_oi_15s_pct": ce_15s_pct_change,
            "ce_delta_ltp_15s": delta_15s_ce_ltp,
            "ce_session_delta_oi": session_delta_ce_oi,
            "ce_buildup": ce_buildup,
            "ce_iv": round(ce_iv, 2),
            "pe_ltp": round(pe_ltp, 2),
            "pe_delta_ltp": delta_pe_ltp,
            "pe_oi": pe_oi,
            "pe_delta_oi": delta_pe_oi,
            "pe_delta_oi_pct": pe_oi_pct_change,
            "pe_delta_oi_15s": delta_15s_pe_oi,
            "pe_delta_oi_15s_pct": pe_15s_pct_change,
            "pe_delta_ltp_15s": delta_15s_pe_ltp,
            "pe_session_delta_oi": session_delta_pe_oi,
            "pe_buildup": pe_buildup,
            "pe_iv": round(pe_iv, 2),
        })

    # Sort strikes ascending
    processed_strikes.sort(key=lambda x: x["strike"])

    # Derived Analytics
    max_pain_result = calculate_max_pain(processed_strikes)
    pcr_result = calculate_pcr(processed_strikes, atm_strike, atm_band_width=atm_band_width)
    iv_skew_result = calculate_iv_skew(processed_strikes, spot_price, atm_strike)

    return {
        "spot_price": round(spot_price, 2),
        "atm_strike": atm_strike,
        "strikes": processed_strikes,
        "max_pain": max_pain_result["max_pain_strike"],
        "max_pain_details": max_pain_result,
        "pcr": pcr_result,
        "iv_skew": iv_skew_result,
        "strike_count": len(processed_strikes)
    }
