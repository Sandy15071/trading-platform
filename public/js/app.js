// Dashboard UI Orchestrator & State Manager with Indian Numbering System (Lakhs & Crores)

function formatIndianCompact(val, decimals = 2) {
  if (val === null || val === undefined || isNaN(val)) return "-";
  const num = Math.abs(Number(val));
  const sign = Number(val) < 0 ? "-" : "";
  if (num >= 10000000) { // 1 Crore = 10,000,000
    return `${sign}${(num / 10000000).toFixed(decimals)} Cr`;
  } else if (num >= 100000) { // 1 Lakh = 100,000
    return `${sign}${(num / 100000).toFixed(decimals)} L`;
  } else if (num >= 1000) {
    return `${sign}${Number(val).toLocaleString("en-IN")}`;
  }
  return sign + num.toString();
}

function formatIndianNumber(val) {
  if (val === null || val === undefined || isNaN(val)) return "-";
  return Number(val).toLocaleString("en-IN");
}

class DashboardApp {
  constructor() {
    this.currentSymbol = "NIFTY";
    this.snapshot = null;
    this.historyData = [];
    this.signalLog = [];
    this.pollInterval = 1;
    this.timeUntilPoll = 1;
    this.countdownTimer = null;
    this.fallbackInterval = null;
    this.alertingRows = new Set();
  }

  async init() {
    console.log("Initializing Option Chain Momentum Indicator...");

    this._bindEvents();
    await this._loadInitialState();
    this._startWebSocket();
    this._startCountdown();
    this._startPollingFallback();

    // Request notification permission on first user click anywhere
    document.addEventListener("click", () => {
      if (window.desktopNotifications.permission === "default") {
        window.desktopNotifications.requestPermission();
      }
    }, { once: true });
  }

  async _loadInitialState() {
    try {
      const urlParams = new URLSearchParams(window.location.search);
      const urlAccessToken = urlParams.get("access_token");
      if (urlAccessToken) {
        localStorage.setItem("kite_access_token", urlAccessToken);
        console.log("Kite access token saved to localStorage from redirect callback.");
      }

      if (urlParams.get("auth") === "success" || urlAccessToken) {
        window.history.replaceState({}, document.title, window.location.pathname);
        console.log("Kite Connect authenticated successfully.");
      } else if (urlParams.get("auth") === "error") {
        alert("❌ Kite Authentication Error: " + (urlParams.get("msg") || "Unknown error"));
        window.history.replaceState({}, document.title, window.location.pathname);
      } else if (urlParams.get("request_token")) {
        try {
          const res = await window.apiService.exchangeToken(urlParams.get("request_token"));
          if (res && res.access_token) {
            localStorage.setItem("kite_access_token", res.access_token);
          }
          window.history.replaceState({}, document.title, window.location.pathname);
        } catch (e) {
          console.error("Auto exchange error:", e);
        }
      }

      // Safe individual fetching
      let status = null, chain = null, history = null, signals = null, config = null;
      try { status = await window.apiService.getStatus(); } catch (e) { console.warn("Status fetch error:", e); }
      try { chain = await window.apiService.getOptionChain(); } catch (e) { console.warn("Chain fetch error:", e); }
      try { history = await window.apiService.getHistory(); } catch (e) { console.warn("History fetch error:", e); }
      try { signals = await window.apiService.getSignals(); } catch (e) { console.warn("Signals fetch error:", e); }
      try { config = await window.apiService.getConfig(); } catch (e) { console.warn("Config fetch error:", e); }

      if (status) {
        this.currentSymbol = status.current_symbol || "NIFTY";
        this.pollInterval = status.poll_interval_seconds || 1;
        this.timeUntilPoll = this.pollInterval;
        this._updateStatusBadge(status);
      } else {
        this._updateStatusBadge({ authenticated: false, mock_mode: true });
      }

      if (config) {
        this._populateConfigForm(config);
      }

      if (chain) {
        this.snapshot = chain;
        this.renderAll();
      }
      if (history && history.history) {
        this.historyData = history.history;
        this.renderCharts();
      }
      if (signals && signals.signals) {
        this.signalLog = signals.signals;
        this.renderSignalFeed();
      }
    } catch (e) {
      console.error("Failed to load initial dashboard state:", e);
    }
  }

  _startPollingFallback() {
    if (this.fallbackInterval) clearInterval(this.fallbackInterval);
    this.fallbackInterval = setInterval(async () => {
      // If WebSocket is not OPEN (e.g. Serverless / Vercel), continuously poll via HTTP
      if (!window.apiService.ws || window.apiService.ws.readyState !== WebSocket.OPEN) {
        try {
          const chain = await window.apiService.getOptionChain();
          if (chain) {
            this.snapshot = chain;
            this.renderAll();
          }
          const status = await window.apiService.getStatus();
          if (status) this._updateStatusBadge(status);
        } catch (e) {
          console.warn("Polling cycle warning:", e);
        }
      }
    }, Math.max(1000, this.pollInterval * 1000));
  }

  _startWebSocket() {
    window.apiService.connectWebSocket((evt) => {
      if (evt.type === "CYCLE_UPDATE" || evt.type === "SNAPSHOT") {
        this.snapshot = evt.data;
        if (evt.symbol) this.currentSymbol = evt.symbol;
        if (evt.history) this.historyData = evt.history;
        if (evt.all_signals) this.signalLog = evt.all_signals;
        if (evt.poll_interval_seconds !== undefined) this.pollInterval = evt.poll_interval_seconds;
        this.timeUntilPoll = this.pollInterval;

        this.renderAll();

        // Process newly fired signals
        if (evt.new_signals && evt.new_signals.length > 0) {
          this._handleNewSignals(evt.new_signals);
        }
      } else if (evt.type === "NEW_SIGNALS") {
        if (evt.signals && evt.signals.length > 0) {
          this._handleNewSignals(evt.signals);
        }
      }
    });
  }

  _handleNewSignals(signals) {
    signals.forEach(sig => {
      // 1. Channel 1: On-Screen Highlight (Table row & Chart bar)
      if (sig.strike) {
        this.alertingRows.add(sig.strike);
        window.optionCharts.setAlertingStrike(sig.strike);
        setTimeout(() => {
          this.alertingRows.delete(sig.strike);
          this.renderTable();
          this.renderOIChart();
        }, 8000);
      }

      // 2. Channel 2: Desktop Push Notification
      window.desktopNotifications.notify(sig, this.currentSymbol);

      // 3. Channel 3: Synthesized Audio Chime
      window.soundAlerts.playAlert(sig.severity || "HIGH");
    });

    // Re-render table and signal feed
    this.renderTable();
    this.renderOIChart();
    this.renderSignalFeed();
  }

  _startCountdown() {
    if (this.countdownTimer) clearInterval(this.countdownTimer);
    this.countdownTimer = setInterval(() => {
      if (this.timeUntilPoll > 0) {
        this.timeUntilPoll -= 1;
      }
      const el = document.getElementById("pollCountdown");
      if (el) el.textContent = `${this.timeUntilPoll}s`;
    }, 1000);
  }

  _updateStatusBadge(status) {
    const dot = document.getElementById("statusDot");
    const label = document.getElementById("statusLabel");
    if (!dot || !label) return;

    const hasStoredToken = Boolean(localStorage.getItem("kite_access_token"));

    if ((status && status.authenticated) || hasStoredToken) {
      dot.className = "status-dot live";
      label.textContent = "KITE LIVE";
    } else {
      dot.className = "status-dot";
      label.textContent = "LOGIN REQUIRED";
    }
  }

  renderAll() {
    this.renderHeader();
    this.renderMetricCards();
    this.renderOIChart();
    this.renderTable();
    this.renderCharts();
    this.renderSignalFeed();
  }

  renderHeader() {
    if (!this.snapshot) return;

    const spotEl = document.getElementById("headerSpotPrice");
    if (spotEl) spotEl.textContent = this.snapshot.spot_price.toLocaleString("en-IN", { minimumFractionDigits: 2 });

    // Update active symbol button
    document.querySelectorAll(".symbol-btn").forEach(btn => {
      if (btn.dataset.symbol === this.currentSymbol) {
        btn.classList.add("active");
      } else {
        btn.classList.remove("active");
      }
    });
  }

  renderMetricCards() {
    if (!this.snapshot) return;

    const spot = this.snapshot.spot_price;
    const atm = this.snapshot.atm_strike;
    const maxPain = this.snapshot.max_pain;
    const pcr = this.snapshot.pcr || {};
    const totalPcr = pcr.total_pcr || 1.0;
    const nearPcr = pcr.near_atm_pcr || 1.0;

    // Spot Card
    const spotValEl = document.getElementById("cardSpotVal");
    if (spotValEl) spotValEl.textContent = spot.toLocaleString("en-IN", { minimumFractionDigits: 2 });

    // PCR Card
    const pcrValEl = document.getElementById("cardPcrVal");
    const pcrTagEl = document.getElementById("cardPcrTag");
    const pcrNearEl = document.getElementById("cardPcrNear");
    const pcrCard = document.getElementById("cardPcr");

    if (pcrValEl) pcrValEl.textContent = totalPcr.toFixed(2);
    if (pcrNearEl) pcrNearEl.textContent = `Near-ATM: ${nearPcr.toFixed(2)}`;

    if (pcrTagEl && pcrCard) {
      if (totalPcr >= 1.2) {
        pcrTagEl.textContent = "BULLISH";
        pcrTagEl.className = "badge-tag badge-bullish";
        pcrCard.className = "metric-card bullish";
      } else if (totalPcr <= 0.8) {
        pcrTagEl.textContent = "BEARISH";
        pcrTagEl.className = "badge-tag badge-bearish";
        pcrCard.className = "metric-card bearish";
      } else {
        pcrTagEl.textContent = "NEUTRAL";
        pcrTagEl.className = "badge-tag badge-neutral";
        pcrCard.className = "metric-card";
      }
    }

    // Max Pain Card
    const painValEl = document.getElementById("cardMaxPainVal");
    const painSubEl = document.getElementById("cardMaxPainSub");
    if (painValEl) painValEl.textContent = formatIndianNumber(maxPain);
    if (painSubEl) {
      const diff = maxPain - spot;
      painSubEl.textContent = `${diff >= 0 ? "+" : ""}${diff.toFixed(0)} pts vs Spot`;
    }

    // ATM Straddle Card
    const atmValEl = document.getElementById("cardAtmVal");
    const atmSubEl = document.getElementById("cardAtmSub");
    if (atmValEl) atmValEl.textContent = formatIndianNumber(atm);

    if (atmSubEl && this.snapshot.strikes) {
      const atmRow = this.snapshot.strikes.find(s => s.strike === atm);
      if (atmRow) {
        const straddlePremium = (atmRow.ce_ltp + atmRow.pe_ltp).toFixed(1);
        atmSubEl.textContent = `Straddle: ₹${straddlePremium} (CE: ₹${atmRow.ce_ltp} | PE: ₹${atmRow.pe_ltp})`;
      }
    }

    // Alerts Card
    const alertsValEl = document.getElementById("cardAlertsVal");
    if (alertsValEl) alertsValEl.textContent = this.signalLog.length.toString();
  }

  renderOIChart() {
    window.optionCharts.renderOIBarChart("oiBarCanvas", this.snapshot);
  }

  renderTable() {
    const tbody = document.getElementById("optionChainTableBody");
    if (!tbody || !this.snapshot || !this.snapshot.strikes) return;

    const strikes = this.snapshot.strikes;
    const maxPain = this.snapshot.max_pain;
    const atmStrike = this.snapshot.atm_strike;

    let html = "";
    strikes.forEach(st => {
      const isATM = st.is_atm || st.strike === atmStrike;
      const isMaxPain = st.strike === maxPain;
      const isAlerting = this.alertingRows.has(st.strike);

      let rowClass = "";
      if (isAlerting) rowClass += " row-alert-flash";
      if (isATM) rowClass += " row-atm";
      if (isMaxPain) rowClass += " row-max-pain";

      const ceDeltaClass = st.ce_delta_oi > 0 ? "delta-pos" : (st.ce_delta_oi < 0 ? "delta-neg" : "");
      const peDeltaClass = st.pe_delta_oi > 0 ? "delta-pos" : (st.pe_delta_oi < 0 ? "delta-neg" : "");

      const ceDeltaStr = st.ce_delta_oi !== 0
        ? `${st.ce_delta_oi > 0 ? "+" : ""}${(st.ce_delta_oi / 100000).toFixed(2)} (${st.ce_delta_oi_pct > 0 ? "+" : ""}${st.ce_delta_oi_pct}%)`
        : "-";
      const peDeltaStr = st.pe_delta_oi !== 0
        ? `${st.pe_delta_oi > 0 ? "+" : ""}${(st.pe_delta_oi / 100000).toFixed(2)} (${st.pe_delta_oi_pct > 0 ? "+" : ""}${st.pe_delta_oi_pct}%)`
        : "-";

      const ceOiLakhs = (st.ce_oi / 100000).toFixed(2);
      const peOiLakhs = (st.pe_oi / 100000).toFixed(2);

      html += `
        <tr class="${rowClass.trim()}">
          <td>${st.ce_iv}%</td>
          <td class="${ceDeltaClass}" title="${formatIndianNumber(st.ce_delta_oi)} contracts">${ceDeltaStr}</td>
          <td style="font-weight:700; color:#10b981; font-size:12.5px;" title="${formatIndianNumber(st.ce_oi)} contracts">${ceOiLakhs}</td>
          <td style="color:#ffffff;">₹${st.ce_ltp.toFixed(2)}</td>
          <td class="strike-cell">${formatIndianNumber(st.strike)}</td>
          <td style="color:#ffffff;">₹${st.pe_ltp.toFixed(2)}</td>
          <td style="font-weight:700; color:#f43f5e; font-size:12.5px;" title="${formatIndianNumber(st.pe_oi)} contracts">${peOiLakhs}</td>
          <td class="${peDeltaClass}" title="${formatIndianNumber(st.pe_delta_oi)} contracts">${peDeltaStr}</td>
          <td>${st.pe_iv}%</td>
        </tr>
      `;
    });

    tbody.innerHTML = html;
  }

  renderCharts() {
    if (this.snapshot && this.snapshot.iv_skew) {
      window.optionCharts.renderIVSkewChart("ivSkewCanvas", this.snapshot.iv_skew, this.snapshot.spot_price);
    }
    if (this.historyData && this.historyData.length > 0) {
      window.optionCharts.renderPCRSparkline("pcrSparklineCanvas", this.historyData);
    }
  }

  renderSignalFeed() {
    const feed = document.getElementById("signalFeed");
    if (!feed) return;

    if (!this.signalLog || this.signalLog.length === 0) {
      feed.innerHTML = `<div class="empty-state">No momentum alerts fired yet. Monitoring live cycle shifts...</div>`;
      return;
    }

    let html = "";
    this.signalLog.slice(0, 20).forEach(sig => {
      html += `
        <div class="signal-item ${sig.severity || 'HIGH'}">
          <div class="signal-item-header">
            <span class="signal-type-tag">${sig.rule_type || 'MOMENTUM'} • ${sig.strike || ''} ${sig.side || ''}</span>
            <span class="signal-time">${sig.time_str || ''}</span>
          </div>
          <div class="signal-msg">${sig.message || ''}</div>
        </div>
      `;
    });

    feed.innerHTML = html;
  }

  _bindEvents() {
    // Symbol switch buttons
    document.querySelectorAll(".symbol-btn").forEach(btn => {
      btn.addEventListener("click", async () => {
        const sym = btn.dataset.symbol;
        if (sym && sym !== this.currentSymbol) {
          try {
            await window.apiService.selectSymbol(sym);
            this.currentSymbol = sym;
            this.snapshot = await window.apiService.getOptionChain();
            this.renderAll();
          } catch (e) {
            console.error("Error switching symbol:", e);
          }
        }
      });
    });

    // Sound toggle button
    const soundBtn = document.getElementById("soundToggleBtn");
    if (soundBtn) {
      soundBtn.addEventListener("click", () => {
        const enabled = window.soundAlerts.toggle();
        soundBtn.classList.toggle("active", enabled);
        soundBtn.title = enabled ? "Sound Alerts: Enabled" : "Sound Alerts: Muted";
      });
    }

    // Test Alert button
    const testBtn = document.getElementById("testAlertBtn");
    if (testBtn) {
      testBtn.addEventListener("click", async () => {
        try {
          const atm = this.snapshot ? this.snapshot.atm_strike : 24500.0;
          await window.apiService.simulateSignal("OI_SURGE", atm);
        } catch (e) {
          console.error("Error triggering simulated alert:", e);
        }
      });
    }

    // Settings Modal
    const settingsBtn = document.getElementById("settingsBtn");
    const settingsModal = document.getElementById("settingsModal");
    const closeSettingsBtn = document.getElementById("closeSettingsBtn");
    const saveSettingsBtn = document.getElementById("saveSettingsBtn");

    if (settingsBtn && settingsModal) {
      settingsBtn.addEventListener("click", () => settingsModal.classList.add("open"));
    }
    if (closeSettingsBtn && settingsModal) {
      closeSettingsBtn.addEventListener("click", () => settingsModal.classList.remove("open"));
    }
    if (saveSettingsBtn && settingsModal) {
      saveSettingsBtn.addEventListener("click", async () => {
        await this._saveConfigForm();
        settingsModal.classList.remove("open");
      });
    }

    // Kite Auth Modal
    const kiteAuthBtn = document.getElementById("kiteAuthBtn");
    const authModal = document.getElementById("authModal");
    const closeAuthBtn = document.getElementById("closeAuthBtn");
    const openLoginUrlBtn = document.getElementById("openLoginUrlBtn");
    const submitTokenBtn = document.getElementById("submitTokenBtn");

    if (kiteAuthBtn && authModal) {
      kiteAuthBtn.addEventListener("click", () => authModal.classList.add("open"));
    }
    if (closeAuthBtn && authModal) {
      closeAuthBtn.addEventListener("click", () => authModal.classList.remove("open"));
    }
    if (openLoginUrlBtn) {
      openLoginUrlBtn.addEventListener("click", () => {
        window.location.href = "https://kite.zerodha.com/connect/login?v=3&api_key=8u08ywqp1fuc7xvc";
      });
    }
    if (submitTokenBtn && authModal) {
      submitTokenBtn.addEventListener("click", async () => {
        const tokenInput = document.getElementById("requestTokenInput");
        const token = tokenInput ? tokenInput.value.trim() : "";
        if (!token) return alert("Please enter the request_token from URL");

        try {
          const res = await window.apiService.exchangeToken(token);
          if (res && res.access_token) {
            localStorage.setItem("kite_access_token", res.access_token);
          }
          alert("Successfully authenticated with Zerodha Kite Connect!");
          authModal.classList.remove("open");
          const [status, chain] = await Promise.all([
            window.apiService.getStatus(),
            window.apiService.getOptionChain()
          ]);
          if (status) this._updateStatusBadge(status);
          if (chain) {
            this.snapshot = chain;
            this.renderAll();
          }
        } catch (e) {
          alert("Authentication failed: " + e.message);
        }
      });
    }

    // Resize listener for responsive charts
    window.addEventListener("resize", () => {
      this.renderOIChart();
      this.renderCharts();
    });
  }

  _populateConfigForm(configData) {
    if (!configData || !configData.config) return;
    const cfg = configData.config;
    const rules = cfg.rules || {};

    const setVal = (id, val) => {
      const el = document.getElementById(id);
      if (el && val !== undefined) el.value = val;
    };

    setVal("cfgPollInterval", cfg.poll_interval_seconds);
    setVal("cfgOISurge", rules.oi_surge_pct);
    setVal("cfgPcrBull", rules.pcr_bullish_threshold);
    setVal("cfgPcrBear", rules.pcr_bearish_threshold);
    setVal("cfgPcrDelta", rules.pcr_delta_threshold);
    setVal("cfgIvSpike", rules.iv_spike_pct);
    setVal("cfgAtmImbalance", rules.atm_imbalance_ratio);
  }

  async _saveConfigForm() {
    const getVal = (id, isFloat = true) => {
      const el = document.getElementById(id);
      if (!el) return null;
      return isFloat ? parseFloat(el.value) : el.value;
    };

    const payload = {
      poll_interval_seconds: parseInt(getVal("cfgPollInterval", false)),
      mock_mode: document.getElementById("cfgMockMode")?.value === "true",
      rules: {
        oi_surge_pct: getVal("cfgOISurge"),
        pcr_bullish_threshold: getVal("cfgPcrBull"),
        pcr_bearish_threshold: getVal("cfgPcrBear"),
        pcr_delta_threshold: getVal("cfgPcrDelta"),
        iv_spike_pct: getVal("cfgIvSpike"),
        atm_imbalance_ratio: getVal("cfgAtmImbalance"),
        max_pain_drift_enabled: true
      }
    };

    const tgToken = document.getElementById("cfgTgToken")?.value?.trim();
    const tgChat = document.getElementById("cfgTgChat")?.value?.trim();
    if (tgToken) payload.telegram_bot_token = tgToken;
    if (tgChat) payload.telegram_chat_id = tgChat;

    try {
      const res = await window.apiService.updateConfig(payload);
      this.pollInterval = payload.poll_interval_seconds || 1;
      this._updateStatusBadge(await window.apiService.getStatus());
      console.log("Config updated successfully:", res);
    } catch (e) {
      console.error("Error saving config:", e);
    }
  }
}

document.addEventListener("DOMContentLoaded", () => {
  window.app = new DashboardApp();
  window.app.init();
});
