import time
import uuid
from typing import List, Dict, Any, Optional
from backend.services.history_buffer import HistoryBuffer

def format_indian_number(num: int | float) -> str:
    """Formats an integer or float using Indian grouping (e.g. 1,32,95,230)."""
    try:
        n = int(round(num))
        is_neg = n < 0
        s = str(abs(n))
        if len(s) <= 3:
            res = s
        else:
            last_three = s[-3:]
            remaining = s[:-3]
            chunks = []
            while remaining:
                chunks.insert(0, remaining[-2:])
                remaining = remaining[:-2]
            res = ",".join(chunks) + "," + last_three
        return ("-" if is_neg else "") + res
    except Exception:
        return f"{num:,.0f}"

def format_indian_compact(num: int | float) -> str:
    """Formats large numbers into Lakhs (L) and Crores (Cr) (e.g. 1.33 Cr, 46.93 L)."""
    try:
        n = abs(float(num))
        sign = "-" if num < 0 else ""
        if n >= 10000000:
            return f"{sign}{n / 10000000:.2f} Cr"
        elif n >= 100000:
            return f"{sign}{n / 100000:.2f} L"
        else:
            return format_indian_number(num)
    except Exception:
        return str(num)

class MomentumEngine:
    def __init__(self, history_buffer: HistoryBuffer):
        self.history = history_buffer
        self.signal_log: List[Dict[str, Any]] = []
        self.max_signal_log_size = 100
        # Deduplication tracker: {rule_key: last_triggered_timestamp}
        self.last_triggered: Dict[str, float] = {}
        self.dedup_cooldown_seconds = 45.0  # Prevent spamming identical rule on consecutive cycles

    def evaluate_rules(
        self,
        current_snapshot: Dict[str, Any],
        rules_config: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Runs all 5 PRD momentum rules against the latest option chain data.
        Returns a list of newly fired signals.
        """
        latest_in_history = self.history.get_latest()
        if latest_in_history and (
            latest_in_history is current_snapshot or
            latest_in_history.get("timestamp") == current_snapshot.get("timestamp")
        ):
            prev_snapshot = self.history.get_previous()
        else:
            prev_snapshot = latest_in_history

        new_signals: List[Dict[str, Any]] = []
        now = time.time()
        time_str = time.strftime("%H:%M:%S")

        spot = current_snapshot.get("spot_price", 0.0)
        atm_strike = current_snapshot.get("atm_strike", 0.0)
        strikes = current_snapshot.get("strikes", [])
        pcr_data = current_snapshot.get("pcr", {})
        curr_pcr = pcr_data.get("total_pcr", 1.0)
        curr_near_pcr = pcr_data.get("near_atm_pcr", 1.0)
        curr_max_pain = current_snapshot.get("max_pain", 0.0)

        # -------------------------------------------------------------
        # Rule 1: OI Surge (FR-13)
        # -------------------------------------------------------------
        oi_surge_threshold = float(rules_config.get("oi_surge_pct", 8.0))
        for st in strikes:
            strike = st["strike"]
            # Call side
            ce_pct = st.get("ce_delta_oi_pct", 0.0)
            ce_delta = st.get("ce_delta_oi", 0)
            if abs(ce_pct) >= oi_surge_threshold and abs(ce_delta) >= 1000:
                direction = "Build-up (Call Writing)" if ce_delta > 0 else "Unwinding (Short Covering / Long Unwind)"
                rule_key = f"OI_SURGE_{strike}_CE_{'POS' if ce_delta > 0 else 'NEG'}"
                if now - self.last_triggered.get(rule_key, 0) > self.dedup_cooldown_seconds:
                    sig = {
                        "id": str(uuid.uuid4())[:8],
                        "timestamp": now,
                        "time_str": time_str,
                        "strike": strike,
                        "side": "CE",
                        "rule_type": "OI_SURGE",
                        "severity": "HIGH" if abs(ce_pct) >= oi_surge_threshold * 1.5 else "MEDIUM",
                        "direction": direction,
                        "message": f"CE {format_indian_number(strike)} ΔOI surged {ce_pct:+.1f}% ({format_indian_compact(ce_delta)} contracts) - {direction}",
                        "details": {"pct_change": ce_pct, "delta_oi": ce_delta, "oi": st.get("ce_oi", 0)}
                    }
                    new_signals.append(sig)
                    self.last_triggered[rule_key] = now

            # Put side
            pe_pct = st.get("pe_delta_oi_pct", 0.0)
            pe_delta = st.get("pe_delta_oi", 0)
            if abs(pe_pct) >= oi_surge_threshold and abs(pe_delta) >= 1000:
                direction = "Build-up (Put Writing)" if pe_delta > 0 else "Unwinding (Put Unwinding)"
                rule_key = f"OI_SURGE_{strike}_PE_{'POS' if pe_delta > 0 else 'NEG'}"
                if now - self.last_triggered.get(rule_key, 0) > self.dedup_cooldown_seconds:
                    sig = {
                        "id": str(uuid.uuid4())[:8],
                        "timestamp": now,
                        "time_str": time_str,
                        "strike": strike,
                        "side": "PE",
                        "rule_type": "OI_SURGE",
                        "severity": "HIGH" if abs(pe_pct) >= oi_surge_threshold * 1.5 else "MEDIUM",
                        "direction": direction,
                        "message": f"PE {format_indian_number(strike)} ΔOI surged {pe_pct:+.1f}% ({format_indian_compact(pe_delta)} contracts) - {direction}",
                        "details": {"pct_change": pe_pct, "delta_oi": pe_delta, "oi": st.get("pe_oi", 0)}
                    }
                    new_signals.append(sig)
                    self.last_triggered[rule_key] = now

        # -------------------------------------------------------------
        # Rule 2: PCR Threshold Cross & Jump (FR-14)
        # -------------------------------------------------------------
        pcr_bull = float(rules_config.get("pcr_bullish_threshold", 1.2))
        pcr_bear = float(rules_config.get("pcr_bearish_threshold", 0.8))
        pcr_delta_thresh = float(rules_config.get("pcr_delta_threshold", 0.15))

        if prev_snapshot:
            prev_pcr = prev_snapshot.get("pcr", {}).get("total_pcr", 1.0)
            pcr_change = curr_pcr - prev_pcr

            # Crossing into Bullish territory (> 1.2)
            if curr_pcr >= pcr_bull and prev_pcr < pcr_bull:
                rule_key = "PCR_CROSS_BULLISH"
                if now - self.last_triggered.get(rule_key, 0) > self.dedup_cooldown_seconds:
                    sig = {
                        "id": str(uuid.uuid4())[:8],
                        "timestamp": now,
                        "time_str": time_str,
                        "strike": atm_strike,
                        "side": "BOTH",
                        "rule_type": "PCR_CROSS",
                        "severity": "HIGH",
                        "direction": "BULLISH",
                        "message": f"PCR crossed into Bullish zone at {curr_pcr:.2f} (threshold: >{pcr_bull})",
                        "details": {"curr_pcr": curr_pcr, "prev_pcr": prev_pcr}
                    }
                    new_signals.append(sig)
                    self.last_triggered[rule_key] = now

            # Crossing into Bearish territory (< 0.8)
            elif curr_pcr <= pcr_bear and prev_pcr > pcr_bear:
                rule_key = "PCR_CROSS_BEARISH"
                if now - self.last_triggered.get(rule_key, 0) > self.dedup_cooldown_seconds:
                    sig = {
                        "id": str(uuid.uuid4())[:8],
                        "timestamp": now,
                        "time_str": time_str,
                        "strike": atm_strike,
                        "side": "BOTH",
                        "rule_type": "PCR_CROSS",
                        "severity": "HIGH",
                        "direction": "BEARISH",
                        "message": f"PCR crossed into Bearish zone at {curr_pcr:.2f} (threshold: <{pcr_bear})",
                        "details": {"curr_pcr": curr_pcr, "prev_pcr": prev_pcr}
                    }
                    new_signals.append(sig)
                    self.last_triggered[rule_key] = now

            # Sharp single-cycle PCR jump
            if abs(pcr_change) >= pcr_delta_thresh:
                rule_key = f"PCR_JUMP_{'UP' if pcr_change > 0 else 'DOWN'}"
                if now - self.last_triggered.get(rule_key, 0) > self.dedup_cooldown_seconds:
                    bias = "Bullish Shift (Heavy Put addition / Call exit)" if pcr_change > 0 else "Bearish Shift (Heavy Call addition / Put exit)"
                    sig = {
                        "id": str(uuid.uuid4())[:8],
                        "timestamp": now,
                        "time_str": time_str,
                        "strike": atm_strike,
                        "side": "BOTH",
                        "rule_type": "PCR_JUMP",
                        "severity": "MEDIUM",
                        "direction": "BULLISH" if pcr_change > 0 else "BEARISH",
                        "message": f"PCR shifted sharply by {pcr_change:+.2f} in 1 cycle ({prev_pcr:.2f} -> {curr_pcr:.2f}) - {bias}",
                        "details": {"pcr_change": pcr_change, "curr_pcr": curr_pcr, "prev_pcr": prev_pcr}
                    }
                    new_signals.append(sig)
                    self.last_triggered[rule_key] = now

        # -------------------------------------------------------------
        # Rule 3: Max Pain Drift (FR-15)
        # -------------------------------------------------------------
        max_pain_enabled = rules_config.get("max_pain_drift_enabled", True)
        if max_pain_enabled and prev_snapshot:
            prev_max_pain = prev_snapshot.get("max_pain", 0.0)
            if prev_max_pain > 0 and curr_max_pain != prev_max_pain:
                prev_distance = abs(prev_max_pain - spot)
                curr_distance = abs(curr_max_pain - spot)
                drift_dir = "TOWARD spot" if curr_distance < prev_distance else "AWAY from spot"
                pain_shift = curr_max_pain - prev_max_pain
                
                rule_key = f"MAX_PAIN_DRIFT_{curr_max_pain}"
                if now - self.last_triggered.get(rule_key, 0) > self.dedup_cooldown_seconds:
                    sig = {
                        "id": str(uuid.uuid4())[:8],
                        "timestamp": now,
                        "time_str": time_str,
                        "strike": curr_max_pain,
                        "side": "BOTH",
                        "rule_type": "MAX_PAIN_DRIFT",
                        "severity": "HIGH",
                        "direction": "UPWARD" if pain_shift > 0 else "DOWNWARD",
                        "message": f"Max Pain drifted from {prev_max_pain:.0f} to {curr_max_pain:.0f} ({pain_shift:+.0f} pts, moving {drift_dir})",
                        "details": {"prev_max_pain": prev_max_pain, "curr_max_pain": curr_max_pain, "spot": spot}
                    }
                    new_signals.append(sig)
                    self.last_triggered[rule_key] = now

        # -------------------------------------------------------------
        # Rule 4: IV Spike (FR-16)
        # -------------------------------------------------------------
        iv_spike_threshold = float(rules_config.get("iv_spike_pct", 15.0))
        for st in strikes:
            strike = st["strike"]
            # Call IV Spike
            ce_iv = st.get("ce_iv", 0.0)
            if ce_iv > 0:
                avg_ce_iv = self.history.get_strike_rolling_iv(strike, "CE", window=10)
                if avg_ce_iv and avg_ce_iv > 0:
                    ce_iv_jump = ((ce_iv - avg_ce_iv) / avg_ce_iv) * 100
                    if ce_iv_jump >= iv_spike_threshold:
                        rule_key = f"IV_SPIKE_{strike}_CE"
                        if now - self.last_triggered.get(rule_key, 0) > self.dedup_cooldown_seconds:
                            sig = {
                                "id": str(uuid.uuid4())[:8],
                                "timestamp": now,
                                "time_str": time_str,
                                "strike": strike,
                                "side": "CE",
                                "rule_type": "IV_SPIKE",
                                "severity": "HIGH",
                                "direction": "VOLATILITY_EXPANSION",
                                "message": f"CE {strike} IV spiked +{ce_iv_jump:.1f}% to {ce_iv:.1f}% (10-cycle avg: {avg_ce_iv:.1f}%)",
                                "details": {"current_iv": ce_iv, "avg_iv": avg_ce_iv, "jump_pct": ce_iv_jump}
                            }
                            new_signals.append(sig)
                            self.last_triggered[rule_key] = now

            # Put IV Spike
            pe_iv = st.get("pe_iv", 0.0)
            if pe_iv > 0:
                avg_pe_iv = self.history.get_strike_rolling_iv(strike, "PE", window=10)
                if avg_pe_iv and avg_pe_iv > 0:
                    pe_iv_jump = ((pe_iv - avg_pe_iv) / avg_pe_iv) * 100
                    if pe_iv_jump >= iv_spike_threshold:
                        rule_key = f"IV_SPIKE_{strike}_PE"
                        if now - self.last_triggered.get(rule_key, 0) > self.dedup_cooldown_seconds:
                            sig = {
                                "id": str(uuid.uuid4())[:8],
                                "timestamp": now,
                                "time_str": time_str,
                                "strike": strike,
                                "side": "PE",
                                "rule_type": "IV_SPIKE",
                                "severity": "HIGH",
                                "direction": "VOLATILITY_EXPANSION",
                                "message": f"PE {strike} IV spiked +{pe_iv_jump:.1f}% to {pe_iv:.1f}% (10-cycle avg: {avg_pe_iv:.1f}%)",
                                "details": {"current_iv": pe_iv, "avg_iv": avg_pe_iv, "jump_pct": pe_iv_jump}
                            }
                            new_signals.append(sig)
                            self.last_triggered[rule_key] = now

        # -------------------------------------------------------------
        # Rule 5: ATM OI Imbalance (FR-17)
        # -------------------------------------------------------------
        atm_ratio_threshold = float(rules_config.get("atm_imbalance_ratio", 1.8))
        for st in strikes:
            if st.get("is_atm"):
                ce_oi = st.get("ce_oi", 0)
                pe_oi = st.get("pe_oi", 0)
                if ce_oi > 0 and pe_oi > 0:
                    pe_to_ce = pe_oi / ce_oi
                    ce_to_pe = ce_oi / pe_oi

                    if pe_to_ce >= atm_ratio_threshold:
                        rule_key = f"ATM_IMBALANCE_PE_{atm_strike}"
                        if now - self.last_triggered.get(rule_key, 0) > self.dedup_cooldown_seconds:
                            sig = {
                                "id": str(uuid.uuid4())[:8],
                                "timestamp": now,
                                "time_str": time_str,
                                "strike": atm_strike,
                                "side": "PE",
                                "rule_type": "ATM_IMBALANCE",
                                "severity": "HIGH",
                                "direction": "BULLISH_SUPPORT",
                                "message": f"ATM {format_indian_number(atm_strike)} heavy Put build: Put OI is {pe_to_ce:.2f}x Call OI ({format_indian_compact(pe_oi)} vs {format_indian_compact(ce_oi)})",
                                "details": {"ratio": pe_to_ce, "pe_oi": pe_oi, "ce_oi": ce_oi}
                            }
                            new_signals.append(sig)
                            self.last_triggered[rule_key] = now

                    elif ce_to_pe >= atm_ratio_threshold:
                        rule_key = f"ATM_IMBALANCE_CE_{atm_strike}"
                        if now - self.last_triggered.get(rule_key, 0) > self.dedup_cooldown_seconds:
                            sig = {
                                "id": str(uuid.uuid4())[:8],
                                "timestamp": now,
                                "time_str": time_str,
                                "strike": atm_strike,
                                "side": "CE",
                                "rule_type": "ATM_IMBALANCE",
                                "severity": "HIGH",
                                "direction": "BEARISH_RESISTANCE",
                                "message": f"ATM {format_indian_number(atm_strike)} heavy Call build: Call OI is {ce_to_pe:.2f}x Put OI ({format_indian_compact(ce_oi)} vs {format_indian_compact(pe_oi)})",
                                "details": {"ratio": ce_to_pe, "ce_oi": ce_oi, "pe_oi": pe_oi}
                            }
                            new_signals.append(sig)
                            self.last_triggered[rule_key] = now

        # Add newly generated signals to internal signal log (most recent first)
        for sig in new_signals:
            self.signal_log.insert(0, sig)

        if len(self.signal_log) > self.max_signal_log_size:
            self.signal_log = self.signal_log[:self.max_signal_log_size]

        return new_signals

    def get_signal_log(self) -> List[Dict[str, Any]]:
        return self.signal_log

    def create_simulated_signal(self, rule_type: str = "OI_SURGE", strike: float = 24500.0) -> Dict[str, Any]:
        """Creates a staged test signal to verify all 4 notification channels."""
        now = time.time()
        time_str = time.strftime("%H:%M:%S")
        sig = {
            "id": str(uuid.uuid4())[:8],
            "timestamp": now,
            "time_str": time_str,
            "strike": strike,
            "side": "PE",
            "rule_type": rule_type,
            "severity": "HIGH",
            "direction": "TEST_TRIGGER",
            "message": f"[TEST SIMULATION] PE {format_indian_number(strike)} ΔOI surged +14.2% (+45.2 L contracts) - Put Build-up",
            "details": {"test": True, "strike": strike}
        }
        self.signal_log.insert(0, sig)
        return sig
