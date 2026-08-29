import logging
import math
import random
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple

try:
    from kiteconnect import KiteConnect
except ImportError:
    KiteConnect = None

from backend.config import config

logger = logging.getLogger("kite_client")

INDEX_CONFIG = {
    "NIFTY": {
        "spot_symbol": "NSE:NIFTY 50",
        "name": "NIFTY",
        "strike_step": 50,
        "base_price": 24500.0,
        "lot_size": 25,
    },
    "BANKNIFTY": {
        "spot_symbol": "NSE:NIFTY BANK",
        "name": "BANKNIFTY",
        "strike_step": 100,
        "base_price": 51200.0,
        "lot_size": 15,
    },
    "FINNIFTY": {
        "spot_symbol": "NSE:NIFTY FIN SERVICE",
        "name": "FINNIFTY",
        "strike_step": 50,
        "base_price": 23600.0,
        "lot_size": 25,
    },
    "MIDCPNIFTY": {
        "spot_symbol": "NSE:NIFTY MID SELECT",
        "name": "MIDCPNIFTY",
        "strike_step": 25,
        "base_price": 12800.0,
        "lot_size": 50,
    }
}

class KiteClientService:
    def __init__(self):
        self.kite: Optional[Any] = None
        self.instruments_cache: Dict[str, Any] = {}
        self.last_instruments_fetch: float = 0
        self.mock_spot_prices: Dict[str, float] = {
            "NIFTY": 24530.0,
            "BANKNIFTY": 51250.0,
            "FINNIFTY": 23620.0,
            "MIDCPNIFTY": 12840.0,
        }
        self.mock_strikes_state: Dict[str, Dict[float, Dict[str, Any]]] = {}
        self._init_kite()

    def _init_kite(self):
        """Initializes the KiteConnect instance with api_key and access_token if available."""
        if KiteConnect and config.kite_api_key:
            try:
                self.kite = KiteConnect(api_key=config.kite_api_key)
                if config.kite_access_token:
                    self.kite.set_access_token(config.kite_access_token)
                logger.info("KiteConnect client initialized")
            except Exception as e:
                logger.error(f"Failed to initialize KiteConnect: {e}")
                self.kite = None

    def get_login_url(self) -> str:
        """Generates Zerodha Kite Connect login URL."""
        if not self.kite and KiteConnect:
            self._init_kite()
        if self.kite:
            try:
                return self.kite.login_url()
            except Exception as e:
                logger.error(f"Error calling self.kite.login_url(): {e}")
        api_key = config.kite_api_key or "8u08ywqp1fuc7xvc"
        return f"https://kite.zerodha.com/connect/login?v=3&api_key={api_key}"

    def exchange_token(self, request_token: str) -> Dict[str, Any]:
        """Exchanges request_token from login redirect for daily access_token."""
        if not self.kite:
            self._init_kite()
        if not self.kite:
            raise ValueError("KiteConnect is not initialized. Please verify KITE_API_KEY in .env")

        try:
            data = self.kite.generate_session(request_token, api_secret=config.kite_api_secret)
            access_token = data.get("access_token")
            if access_token:
                self.kite.set_access_token(access_token)
                config.update_env("KITE_ACCESS_TOKEN", access_token)
                logger.info("Kite session generated and access_token saved successfully")
                return {"status": "success", "user_id": data.get("user_id"), "access_token": access_token}
            else:
                raise ValueError("Access token not returned from Kite session generation")
        except Exception as e:
            logger.error(f"Error generating session with request_token: {e}")
            raise

    def is_authenticated(self) -> bool:
        """Checks if active access token is present."""
        return bool(config.kite_access_token and len(config.kite_access_token) > 10)

    def get_available_symbols(self) -> List[Dict[str, Any]]:
        """Returns list of supported underlying index symbols."""
        symbols = []
        for sym, data in INDEX_CONFIG.items():
            symbols.append({
                "symbol": sym,
                "name": data["name"],
                "strike_step": data["strike_step"],
                "base_price": data["base_price"],
                "lot_size": data["lot_size"]
            })
        return symbols

    def fetch_option_chain_data(self, symbol: str = "NIFTY", expiry: Optional[str] = None) -> Tuple[float, List[Dict[str, Any]]]:
        """
        Fetches or simulates option chain data.
        Returns: (spot_price, raw_strikes_list)
        """
        if config.mock_mode or not self.is_authenticated() or not self.kite:
            return self._generate_mock_option_chain(symbol)
        
        try:
            return self._fetch_live_option_chain(symbol, expiry)
        except Exception as e:
            logger.warning(f"Live Kite fetch failed ({e}). Falling back to simulation mode.")
            return self._generate_mock_option_chain(symbol)

    def _fetch_live_option_chain(self, symbol: str = "NIFTY", expiry: Optional[str] = None) -> Tuple[float, List[Dict[str, Any]]]:
        """Fetches live quotes for ATM ± 10 strikes using Zerodha REST API."""
        cfg = INDEX_CONFIG.get(symbol, INDEX_CONFIG["NIFTY"])
        spot_sym = cfg["spot_symbol"]

        # 1. Fetch Spot Price
        quotes = self.kite.quote([spot_sym])
        spot_quote = quotes.get(spot_sym, {})
        spot_price = float(spot_quote.get("last_price", cfg["base_price"]))

        # 2. Fetch Instruments if cache is older than 4 hours
        now = time.time()
        if not self.instruments_cache or (now - self.last_instruments_fetch) > 14400:
            logger.info("Fetching NFO instrument master list from Kite...")
            nfo_instruments = self.kite.instruments("NFO")
            self.instruments_cache = {
                item["tradingsymbol"]: item for item in nfo_instruments
            }
            self.last_instruments_fetch = now

        # Filter relevant instruments for symbol
        matching_instruments = [
            inst for inst in self.instruments_cache.values() if inst["name"] == symbol
        ]

        if not matching_instruments:
            logger.warning(f"No instruments found for {symbol} in NFO master. Using mock data.")
            return self._generate_mock_option_chain(symbol)

        # Get expiries sorted
        expiries = sorted(list(set(inst["expiry"] for inst in matching_instruments)))
        selected_expiry = expiries[0] if expiries else None
        if expiry:
            for exp in expiries:
                if str(exp) == expiry:
                    selected_expiry = exp
                    break

        expiry_insts = [inst for inst in matching_instruments if inst["expiry"] == selected_expiry]
        available_strikes = sorted(list(set(float(inst["strike"]) for inst in expiry_insts)))

        # Find ATM ± 10 strikes
        step = cfg["strike_step"]
        atm_strike = min(available_strikes, key=lambda x: abs(x - spot_price))
        atm_idx = available_strikes.index(atm_strike)
        start_idx = max(0, atm_idx - 10)
        end_idx = min(len(available_strikes), atm_idx + 11)
        selected_strikes = available_strikes[start_idx:end_idx]

        # Map strikes to CE and PE tradingsymbols
        strike_map: Dict[float, Dict[str, Any]] = {s: {} for s in selected_strikes}
        symbols_to_quote = []

        for inst in expiry_insts:
            st = float(inst["strike"])
            if st in strike_map:
                inst_type = inst["instrument_type"].upper()
                symbol_tag = f"NFO:{inst['tradingsymbol']}"
                strike_map[st][inst_type] = symbol_tag
                symbols_to_quote.append(symbol_tag)

        # Fetch quotes in batch
        opt_quotes = self.kite.quote(symbols_to_quote) if symbols_to_quote else {}

        raw_strikes = []
        for st in sorted(selected_strikes):
            ce_tag = strike_map[st].get("CE")
            pe_tag = strike_map[st].get("PE")

            ce_q = opt_quotes.get(ce_tag, {}) if ce_tag else {}
            pe_q = opt_quotes.get(pe_tag, {}) if pe_tag else {}

            raw_strikes.append({
                "strike": st,
                "ce_ltp": float(ce_q.get("last_price", 0.0)),
                "ce_oi": int(ce_q.get("oi", 0)),
                "ce_iv": self._estimate_iv(spot_price, st, float(ce_q.get("last_price", 0.0)), "CE"),
                "pe_ltp": float(pe_q.get("last_price", 0.0)),
                "pe_oi": int(pe_q.get("oi", 0)),
                "pe_iv": self._estimate_iv(spot_price, st, float(pe_q.get("last_price", 0.0)), "PE"),
            })

        return spot_price, raw_strikes

    def _estimate_iv(self, spot: float, strike: float, ltp: float, option_type: str, dte: float = 3.0) -> float:
        """Approximates IV from market price using simple Newton-Raphson / heuristic for fast display."""
        if ltp <= 0 or spot <= 0 or strike <= 0:
            return 14.5
        
        intrinsic = max(0.0, spot - strike) if option_type == "CE" else max(0.0, strike - spot)
        time_val = max(1.0, ltp - intrinsic)
        t = max(0.01, dte / 365.0)
        
        # Brenner-Subrahmanyam approximation: IV ≈ (TimeValue / (Spot * sqrt(T))) * sqrt(2*pi)
        iv_est = (time_val / (spot * math.sqrt(t))) * 2.5 * 100.0
        return max(5.0, min(80.0, round(iv_est, 1)))

    def _generate_mock_option_chain(self, symbol: str = "NIFTY") -> Tuple[float, List[Dict[str, Any]]]:
        """
        Generates dynamic, realistic option chain market simulation.
        Spot moves with random walk, OI updates with realistic build-up/unwinding dynamics.
        """
        cfg = INDEX_CONFIG.get(symbol, INDEX_CONFIG["NIFTY"])
        step = cfg["strike_step"]

        # Random walk for spot price
        current_spot = self.mock_spot_prices.get(symbol, cfg["base_price"])
        delta_spot = round(random.gauss(0, step * 0.08), 2)
        current_spot = round(current_spot + delta_spot, 2)
        self.mock_spot_prices[symbol] = current_spot

        atm_strike = round(current_spot / step) * step

        # Generate 21 strikes (ATM ± 10)
        strikes_list = [atm_strike + i * step for i in range(-10, 11)]

        if symbol not in self.mock_strikes_state:
            self.mock_strikes_state[symbol] = {}

        state = self.mock_strikes_state[symbol]
        raw_strikes = []

        for st in strikes_list:
            if st not in state:
                # Initialize base OI with standard normal distribution centered near ATM
                dist_factor = math.exp(-((st - current_spot) ** 2) / (2 * (step * 5) ** 2))
                base_ce_oi = int((120000 + random.randint(-15000, 25000)) * (1.0 + (st - current_spot)/(step * 15)) * dist_factor) + 20000
                base_pe_oi = int((120000 + random.randint(-15000, 25000)) * (1.0 - (st - current_spot)/(step * 15)) * dist_factor) + 20000
                base_ce_iv = max(11.0, 15.0 - (st - current_spot)/(step * 10) + random.uniform(-0.5, 0.5))
                base_pe_iv = max(11.0, 15.0 + (current_spot - st)/(step * 10) + random.uniform(-0.5, 0.5))

                state[st] = {
                    "ce_oi": max(5000, base_ce_oi),
                    "pe_oi": max(5000, base_pe_oi),
                    "ce_iv": base_ce_iv,
                    "pe_iv": base_pe_iv
                }

            # Simulate tick update
            st_state = state[st]
            # Small random drift in OI
            ce_oi_change = int(random.gauss(150, 1200))
            pe_oi_change = int(random.gauss(180, 1200))

            st_state["ce_oi"] = max(1000, st_state["ce_oi"] + ce_oi_change)
            st_state["pe_oi"] = max(1000, st_state["pe_oi"] + pe_oi_change)

            # IV drift
            st_state["ce_iv"] = max(8.0, min(50.0, round(st_state["ce_iv"] + random.uniform(-0.3, 0.3), 1)))
            st_state["pe_iv"] = max(8.0, min(50.0, round(st_state["pe_iv"] + random.uniform(-0.3, 0.3), 1)))

            # Theoretical LTP calculation
            intrinsic_ce = max(0.0, current_spot - st)
            time_val_ce = max(2.0, (st_state["ce_iv"] / 100.0) * current_spot * 0.08 * math.exp(-abs(st - current_spot)/(step * 4)))
            ce_ltp = round(intrinsic_ce + time_val_ce, 2)

            intrinsic_pe = max(0.0, st - current_spot)
            time_val_pe = max(2.0, (st_state["pe_iv"] / 100.0) * current_spot * 0.08 * math.exp(-abs(st - current_spot)/(step * 4)))
            pe_ltp = round(intrinsic_pe + time_val_pe, 2)

            raw_strikes.append({
                "strike": float(st),
                "ce_ltp": ce_ltp,
                "ce_oi": st_state["ce_oi"],
                "ce_iv": st_state["ce_iv"],
                "pe_ltp": pe_ltp,
                "pe_oi": st_state["pe_oi"],
                "pe_iv": st_state["pe_iv"],
            })

        return current_spot, raw_strikes

kite_service = KiteClientService()
