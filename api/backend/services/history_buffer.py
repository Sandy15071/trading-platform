from typing import List, Dict, Any, Optional
from collections import deque
import time

class HistoryBuffer:
    def __init__(self, max_size: int = 60):
        self.max_size = max_size
        self.snapshots: deque = deque(maxlen=max_size)
        self.session_open_snapshot: Optional[Dict[str, Any]] = None

    def add_snapshot(self, snapshot: Dict[str, Any]):
        """Append a new processed option chain snapshot with timestamp."""
        payload = {
            "timestamp": time.time(),
            "time_str": time.strftime("%H:%M:%S"),
            **snapshot
        }
        if self.session_open_snapshot is None:
            self.session_open_snapshot = payload
        self.snapshots.append(payload)

    def get_latest(self) -> Optional[Dict[str, Any]]:
        return self.snapshots[-1] if self.snapshots else None

    def get_previous(self) -> Optional[Dict[str, Any]]:
        return self.snapshots[-2] if len(self.snapshots) >= 2 else None

    def get_all(self) -> List[Dict[str, Any]]:
        return list(self.snapshots)

    def get_pcr_history(self) -> List[Dict[str, Any]]:
        """Returns sequence of PCR values over time for sparkline rendering."""
        res = []
        for snap in self.snapshots:
            res.append({
                "timestamp": snap.get("timestamp"),
                "time_str": snap.get("time_str"),
                "total_pcr": snap.get("pcr", {}).get("total_pcr", 1.0),
                "near_atm_pcr": snap.get("pcr", {}).get("near_atm_pcr", 1.0),
                "spot_price": snap.get("spot_price", 0.0),
                "max_pain": snap.get("max_pain", 0.0)
            })
        return res

    def get_strike_rolling_iv(self, strike: float, side: str, window: int = 10) -> Optional[float]:
        """Calculates average IV for a strike over the last N cycles."""
        ivs = []
        key = "ce_iv" if side.upper() == "CE" else "pe_iv"
        recent_snaps = list(self.snapshots)[-window:]
        for snap in recent_snaps:
            for st in snap.get("strikes", []):
                if st["strike"] == strike:
                    iv_val = st.get(key, 0.0)
                    if iv_val > 0:
                        ivs.append(iv_val)
                    break
        if not ivs:
            return None
        return sum(ivs) / len(ivs)

    def get_snapshot_seconds_ago(self, seconds: float = 15.0) -> Optional[Dict[str, Any]]:
        """Finds the snapshot closest to `seconds` ago (e.g. 15s ago)."""
        if not self.snapshots:
            return None
        target_time = time.time() - seconds
        closest = None
        min_diff = float("inf")
        for snap in self.snapshots:
            ts = snap.get("timestamp", 0)
            diff = abs(ts - target_time)
            if diff < min_diff:
                min_diff = diff
                closest = snap
        return closest

    def clear(self):
        self.snapshots.clear()
        self.session_open_snapshot = None

history_buffer = HistoryBuffer()
