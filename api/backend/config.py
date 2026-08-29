import os
import json
from pathlib import Path
from typing import Dict, Any
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

CONFIG_FILE = BASE_DIR / "config.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "symbol": "NIFTY",
    "poll_interval_seconds": 1,
    "history_buffer_size": 60,
    "atm_band_width": 3,
    "rules": {
        "oi_surge_pct": 8.0,
        "pcr_bullish_threshold": 1.2,
        "pcr_bearish_threshold": 0.8,
        "pcr_delta_threshold": 0.15,
        "max_pain_drift_enabled": True,
        "iv_spike_pct": 15.0,
        "atm_imbalance_ratio": 1.8
    },
    "notifications": {
        "sound_enabled": True,
        "browser_push_enabled": True,
        "telegram_enabled": True,
        "on_screen_highlight_duration_seconds": 10
    }
}

class AppConfig:
    def __init__(self):
        self.reload()

    def reload(self):
        load_dotenv(BASE_DIR / ".env", override=True)
        # Environment variables
        self.kite_api_key = os.getenv("KITE_API_KEY", "") or "8u08ywqp1fuc7xvc"
        self.kite_api_secret = os.getenv("KITE_API_SECRET", "") or "p5f0qzu4s27o8i1r5r4q7ic6gucvw3p5"
        self.kite_access_token = os.getenv("KITE_ACCESS_TOKEN", "")
        self.telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        self.mock_mode = os.getenv("MOCK_MODE", "false").lower() in ("true", "1", "yes")
        self.host = os.getenv("HOST", "127.0.0.1")
        self.port = int(os.getenv("PORT", "8000"))

        # File-based dynamic config
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
            except Exception:
                self.data = DEFAULT_CONFIG.copy()
        else:
            self.data = DEFAULT_CONFIG.copy()
            self.save()

    def save(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
        except Exception:
            pass

    def update(self, new_data: Dict[str, Any]):
        def deep_merge(source, destination):
            for k, v in source.items():
                if isinstance(v, dict) and k in destination and isinstance(destination[k], dict):
                    deep_merge(v, destination[k])
                else:
                    destination[k] = v

        deep_merge(new_data, self.data)
        self.save()

    def update_env(self, key: str, value: str):
        try:
            env_file = BASE_DIR / ".env"
            lines = []
            if env_file.exists():
                with open(env_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()
            
            updated = False
            new_lines = []
            for line in lines:
                if line.startswith(f"{key}="):
                    new_lines.append(f"{key}={value}\n")
                    updated = True
                else:
                    new_lines.append(line)
            if not updated:
                new_lines.append(f"{key}={value}\n")

            with open(env_file, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
        except Exception:
            pass

        os.environ[key] = value
        if key == "KITE_ACCESS_TOKEN":
            self.kite_access_token = value
        elif key == "KITE_API_KEY":
            self.kite_api_key = value
        elif key == "KITE_API_SECRET":
            self.kite_api_secret = value
        elif key == "TELEGRAM_BOT_TOKEN":
            self.telegram_bot_token = value
        elif key == "TELEGRAM_CHAT_ID":
            self.telegram_chat_id = value
        elif key == "MOCK_MODE":
            self.mock_mode = value.lower() in ("true", "1", "yes")

config = AppConfig()
