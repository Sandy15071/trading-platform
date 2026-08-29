import logging
import requests
from typing import Dict, Any, List
from backend.config import config

logger = logging.getLogger("notifier")

class NotificationService:
    def __init__(self):
        pass

    def send_telegram_alert(self, signal: Dict[str, Any], symbol: str = "NIFTY") -> bool:
        """Sends a structured alert message to Telegram bot if credentials are configured."""
        bot_token = config.telegram_bot_token or config.data.get("telegram_bot_token", "")
        chat_id = config.telegram_chat_id or config.data.get("telegram_chat_id", "")
        telegram_enabled = config.data.get("notifications", {}).get("telegram_enabled", True)

        if not telegram_enabled:
            return False

        if not bot_token or not chat_id:
            logger.info("Telegram notification skipped: bot_token or chat_id not configured in .env")
            return False

        severity_emoji = "🚨" if signal.get("severity") == "HIGH" else "⚠️"
        rule = signal.get("rule_type", "MOMENTUM_SIGNAL")
        strike = signal.get("strike", "-")
        side = signal.get("side", "")
        time_str = signal.get("time_str", "")
        message_text = signal.get("message", "")

        telegram_msg = (
            f"{severity_emoji} *MOMENTUM ALERT: {symbol}*\n\n"
            f"📌 *Rule:* `{rule}`\n"
            f"🎯 *Strike:* `{strike} {side}`\n"
            f"📊 *Summary:* {message_text}\n"
            f"⏰ *Time:* `{time_str}`\n"
        )

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": telegram_msg,
            "parse_mode": "Markdown"
        }

        try:
            resp = requests.post(url, json=payload, timeout=5)
            if resp.status_code == 200:
                logger.info(f"Telegram alert sent successfully for signal {signal.get('id')}")
                return True
            else:
                logger.warning(f"Telegram API responded with status {resp.status_code}: {resp.text}")
                return False
        except Exception as e:
            logger.error(f"Failed to send Telegram notification: {e}")
            return False

    def dispatch_signals(self, signals: List[Dict[str, Any]], symbol: str = "NIFTY"):
        """Dispatches fired signals across backend channels."""
        for sig in signals:
            self.send_telegram_alert(sig, symbol)

notifier = NotificationService()
