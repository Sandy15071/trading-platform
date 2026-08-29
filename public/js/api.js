// API client and real-time WebSocket connection manager

class ApiService {
  constructor() {
    this.baseUrl = window.location.origin;
    this.ws = null;
    this.wsListeners = [];
    this.reconnectTimer = null;
  }

  async get(endpoint) {
    const headers = {};
    const token = localStorage.getItem("kite_access_token");
    if (token) headers["X-Kite-Access-Token"] = token;

    const res = await fetch(`${this.baseUrl}${endpoint}`, { headers });
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
    return await res.json();
  }

  async post(endpoint, data = {}) {
    const headers = { "Content-Type": "application/json" };
    const token = localStorage.getItem("kite_access_token");
    if (token) headers["X-Kite-Access-Token"] = token;

    const res = await fetch(`${this.baseUrl}${endpoint}`, {
      method: "POST",
      headers,
      body: JSON.stringify(data)
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
    return await res.json();
  }

  // Endpoints
  getStatus() { return this.get("/api/status"); }
  getSymbols() { return this.get("/api/symbols"); }
  selectSymbol(symbol) { return this.post("/api/symbol/select", { symbol }); }
  getOptionChain() { return this.get("/api/option-chain"); }
  getHistory() { return this.get("/api/history"); }
  getSignals() { return this.get("/api/signals"); }
  getConfig() { return this.get("/api/config"); }
  updateConfig(data) { return this.post("/api/config", data); }
  simulateSignal(rule_type, strike) { return this.post("/api/simulate-signal", { rule_type, strike }); }
  getLoginUrl() { return this.post("/api/auth/login-url"); }
  exchangeToken(request_token) { return this.post("/api/auth/exchange", { request_token }); }

  // WebSocket
  connectWebSocket(onMessage) {
    if (onMessage) this.wsListeners.push(onMessage);

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/api/ws`;

    try {
      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        console.log("WebSocket connected to live data stream");
        if (this.reconnectTimer) {
          clearTimeout(this.reconnectTimer);
          this.reconnectTimer = null;
        }
      };

      this.ws.onmessage = (evt) => {
        try {
          const data = JSON.parse(evt.data);
          this.wsListeners.forEach(listener => listener(data));
        } catch (e) {
          console.error("Error parsing WebSocket message:", e);
        }
      };

      this.ws.onclose = () => {
        console.warn("WebSocket disconnected. Reconnecting in 3s...");
        this.reconnectTimer = setTimeout(() => this.connectWebSocket(), 3000);
      };

      this.ws.onerror = (err) => {
        console.error("WebSocket error:", err);
      };
    } catch (e) {
      console.error("Failed to establish WebSocket connection:", e);
    }
  }

  sendPing() {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ action: "PING" }));
    }
  }
}

window.apiService = new ApiService();
