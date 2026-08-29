// Web Notifications API for desktop push alerts
class DesktopNotificationService {
  constructor() {
    this.permission = "default";
    this.enabled = true;
    this._checkPermission();
  }

  _checkPermission() {
    if ("Notification" in window) {
      this.permission = Notification.permission;
    }
  }

  async requestPermission() {
    if (!("Notification" in window)) {
      console.warn("Desktop notifications not supported in this browser.");
      return false;
    }
    try {
      const perm = await Notification.requestPermission();
      this.permission = perm;
      return perm === "granted";
    } catch (e) {
      console.error("Error requesting notification permission:", e);
      return false;
    }
  }

  notify(signal, symbol = "NIFTY") {
    if (!this.enabled) return;
    if (this.permission !== "granted") return;

    try {
      const title = `🚨 ${symbol} Momentum Alert: ${signal.rule_type}`;
      const options = {
        body: signal.message || `Signal triggered on ${signal.strike} ${signal.side}`,
        tag: `signal-${signal.id}`,
        renotify: true,
        silent: true // Audio is handled via Web Audio API synth
      };

      const notification = new Notification(title, options);
      notification.onclick = () => {
        window.focus();
        notification.close();
      };
    } catch (e) {
      console.error("Error displaying notification:", e);
    }
  }
}

window.desktopNotifications = new DesktopNotificationService();
