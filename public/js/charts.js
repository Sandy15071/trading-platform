// Canvas-based real-time financial chart visualizers with Indian Numbering System (Lakhs & Crores)

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

const BUILDUP_CONFIG = {
  LONG_BUILDUP: {
    code: "LB",
    shortLabel: "Long Build",
    fullName: "Long Build-up",
    overlayGradStart: "rgba(16, 185, 129, 0.4)",
    overlayGradEnd: "#10b981",
    borderColor: "#10b981",
    bgBadge: "rgba(16, 185, 129, 0.4)",
    textBadge: "#a7f3d0"
  },
  SHORT_BUILDUP: {
    code: "SB",
    shortLabel: "Short Build",
    fullName: "Short Build-up",
    overlayGradStart: "rgba(244, 63, 94, 0.4)",
    overlayGradEnd: "#f43f5e",
    borderColor: "#f43f5e",
    bgBadge: "rgba(244, 63, 94, 0.4)",
    textBadge: "#fecdd3"
  },
  SHORT_COVERING: {
    code: "SC",
    shortLabel: "Short Cover",
    fullName: "Short Covering",
    overlayGradStart: "rgba(6, 182, 212, 0.4)",
    overlayGradEnd: "#06b6d4",
    borderColor: "#06b6d4",
    bgBadge: "rgba(6, 182, 212, 0.4)",
    textBadge: "#cffafe"
  },
  LONG_UNWINDING: {
    code: "LU",
    shortLabel: "Long Unwind",
    fullName: "Long Unwinding",
    overlayGradStart: "rgba(245, 158, 11, 0.4)",
    overlayGradEnd: "#f59e0b",
    borderColor: "#f59e0b",
    bgBadge: "rgba(245, 158, 11, 0.4)",
    textBadge: "#fef3c7"
  }
};

function getBuildupState(deltaOI, deltaLTP, explicitState) {
  if (explicitState && BUILDUP_CONFIG[explicitState]) {
    return BUILDUP_CONFIG[explicitState];
  }
  if (deltaOI > 0) {
    return (deltaLTP !== undefined && deltaLTP < 0) ? BUILDUP_CONFIG.SHORT_BUILDUP : BUILDUP_CONFIG.LONG_BUILDUP;
  } else if (deltaOI < 0) {
    return (deltaLTP !== undefined && deltaLTP < 0) ? BUILDUP_CONFIG.LONG_UNWINDING : BUILDUP_CONFIG.SHORT_COVERING;
  }
  return null;
}

class OptionChainCharts {
  constructor() {
    this.alertingStrikes = new Set();
  }

  setAlertingStrike(strike) {
    this.alertingStrikes.add(strike);
    setTimeout(() => {
      this.alertingStrikes.delete(strike);
    }, 8000);
  }

  // 1. Side-by-Side Open Interest Horizontal Bars
  renderOIBarChart(canvasId, snapshot) {
    const canvas = document.getElementById(canvasId);
    if (!canvas || !snapshot || !snapshot.strikes) return;

    const ctx = canvas.getContext("2d");
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();

    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);

    const width = rect.width;
    const height = rect.height;
    ctx.clearRect(0, 0, width, height);

    const strikes = snapshot.strikes;
    const count = strikes.length;
    if (count === 0) return;

    const rowHeight = height / count;
    const centerX = width / 2;
    const centerColWidth = 74;
    const barMaxWidth = (width - centerColWidth - 80) / 2;

    // Find max OI for normalization
    let maxOI = 1000;
    strikes.forEach(st => {
      if (st.ce_oi > maxOI) maxOI = st.ce_oi;
      if (st.pe_oi > maxOI) maxOI = st.pe_oi;
    });

    const maxPain = snapshot.max_pain;
    const atmStrike = snapshot.atm_strike;

    strikes.forEach((st, idx) => {
      const y = idx * rowHeight;
      const strike = st.strike;
      const isATM = st.is_atm || strike === atmStrike;
      const isMaxPain = strike === maxPain;
      const isAlerting = this.alertingStrikes.has(strike);

      // Background highlight for ATM / Max Pain / Alert
      if (isAlerting) {
        ctx.fillStyle = "rgba(245, 158, 11, 0.22)";
        ctx.fillRect(0, y, width, rowHeight);
      } else if (isATM) {
        ctx.fillStyle = "rgba(245, 158, 11, 0.08)";
        ctx.fillRect(0, y, width, rowHeight);
      }

      // Row separator line
      ctx.strokeStyle = "rgba(255, 255, 255, 0.04)";
      ctx.beginPath();
      ctx.moveTo(0, y + rowHeight);
      ctx.lineTo(width, y + rowHeight);
      ctx.stroke();

      // Left Bar: Call OI (expands leftwards from center)
      const ceBarWidth = (st.ce_oi / maxOI) * barMaxWidth;
      const ceX = centerX - (centerColWidth / 2) - ceBarWidth;
      const barY = y + 3;
      const barH = rowHeight - 6;

      // Base Call Bar Gradient (Total OI)
      const ceGrad = ctx.createLinearGradient(centerX - (centerColWidth / 2), 0, ceX, 0);
      ceGrad.addColorStop(0, "#047857");
      ceGrad.addColorStop(1, "#059669");

      ctx.fillStyle = ceGrad;
      ctx.beginPath();
      ctx.roundRect(ceX, barY, ceBarWidth, barH, [4, 0, 0, 4]);
      ctx.fill();

      // Superimposed Graphical ΔOI% Overlay on Call Bar
      // Superimposed Graphical ΔOI% Overlay on Call Bar (outer leading edge)
      const ceDelta = st.ce_delta_oi || 0;
      const ceDeltaPct = st.ce_delta_oi_pct || 0;
      let ceOverlayWidth = 0;

      if (ceDelta !== 0 && ceBarWidth > 12) {
        // Proportion of bar representing the delta change
        const deltaFraction = Math.min(0.45, Math.max(0.08, Math.abs(ceDeltaPct) / 100));
        ceOverlayWidth = Math.min(ceBarWidth * 0.45, Math.max(8, ceBarWidth * deltaFraction));
        const overlayX = ceX; // Leading outer edge for build-up

        if (ceDelta > 0) {
          // Positive ΔOI% (Call Build-up) - Glowing Neon Cyan/Teal Overlay
          const overlayGrad = ctx.createLinearGradient(overlayX + ceOverlayWidth, 0, overlayX, 0);
          overlayGrad.addColorStop(0, "rgba(6, 182, 212, 0.3)");
          overlayGrad.addColorStop(1, "#06b6d4");

          ctx.fillStyle = overlayGrad;
          ctx.beginPath();
          ctx.roundRect(overlayX, barY, ceOverlayWidth, barH, [4, 0, 0, 4]);
          ctx.fill();

          // Subtle inner top border glow
          ctx.strokeStyle = "rgba(56, 189, 248, 0.9)";
          ctx.lineWidth = 1.5;
          ctx.stroke();
        } else {
          // Negative ΔOI% (Short Covering / Unwind) - Orange/Amber Hatched Strip
          ctx.fillStyle = "rgba(245, 158, 11, 0.5)";
          ctx.beginPath();
          ctx.roundRect(overlayX, barY, ceOverlayWidth, barH, [4, 0, 0, 4]);
          ctx.fill();

          ctx.strokeStyle = "rgba(245, 158, 11, 0.9)";
          ctx.lineWidth = 1;
          ctx.stroke();
        }
      }

      // Superimposed ΔOI% Badge inside Call Bar (pushed inward into solid bar body to prevent overlay obstruction)
      if (ceDelta !== 0 && ceBarWidth > 58) {
        const isSurge = Math.abs(ceDeltaPct) >= 8.0;
        const badgeText = `${ceDelta > 0 ? "▲ +" : "▼ "}${ceDeltaPct.toFixed(1)}%`;
        ctx.font = "bold 9px JetBrains Mono, monospace";
        const textMetrics = ctx.measureText(badgeText);
        const badgeW = textMetrics.width + 8;
        const badgeH = barH - 4;
        
        // Push badge inward into the solid green bar body (to the right of the overlay)
        let badgeX = ceX + ceOverlayWidth + 6;
        const maxBadgeX = (centerX - (centerColWidth / 2)) - badgeW - 28;
        if (badgeX > maxBadgeX) badgeX = maxBadgeX;

        const badgeY = barY + 2;

        if (badgeX > ceX + 2) {
          // Badge Background
          ctx.fillStyle = isSurge ? "rgba(6, 182, 212, 0.45)" : "rgba(0, 0, 0, 0.7)";
          ctx.strokeStyle = isSurge ? "#06b6d4" : (ceDelta > 0 ? "rgba(16, 185, 129, 0.6)" : "rgba(245, 158, 11, 0.6)");
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.roundRect(badgeX, badgeY, badgeW, badgeH, 3);
          ctx.fill();
          ctx.stroke();

          // Badge Text
          ctx.fillStyle = ceDelta > 0 ? "#67e8f9" : "#fbbf24";
          ctx.textAlign = "center";
          ctx.fillText(badgeText, badgeX + badgeW / 2, badgeY + badgeH - 3);
        }
      }

      // Derivative Build-up State Badge (LB / SB / SC / LU) - Latched to 15-Second Cycle
      const ceBuildup = (st.ce_buildup && BUILDUP_CONFIG[st.ce_buildup]) ? BUILDUP_CONFIG[st.ce_buildup] : null;
      if (ceBuildup) {
        const tagW = 20;
        const tagH = barH - 4;
        const tagX = (centerX - (centerColWidth / 2)) - tagW - 4; // Inner base
        const tagY = barY + 2;

        ctx.fillStyle = ceBuildup.bgBadge;
        ctx.strokeStyle = ceBuildup.borderColor;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.roundRect(tagX, tagY, tagW, tagH, 3);
        ctx.fill();
        ctx.stroke();

        ctx.fillStyle = ceBuildup.textBadge;
        ctx.font = "bold 9px JetBrains Mono, monospace";
        ctx.textAlign = "center";
        ctx.fillText(ceBuildup.code, tagX + tagW / 2, tagY + tagH - 3);
      }

      // Left Bar Label: Call Total OI (in Lakhs, pure number up to 2 decimals)
      const ceLakhs = (st.ce_oi / 100000).toFixed(2);
      ctx.fillStyle = "#a7f3d0";
      ctx.font = "10.5px JetBrains Mono, monospace";
      ctx.textAlign = "right";
      ctx.fillText(ceLakhs, ceX - 6, y + (rowHeight / 2) + 3);

      // Right Bar: Put OI (expands rightwards from center)
      const peBarWidth = (st.pe_oi / maxOI) * barMaxWidth;
      const peX = centerX + (centerColWidth / 2);

      // Base Put Bar Gradient (Total OI)
      const peGrad = ctx.createLinearGradient(peX, 0, peX + peBarWidth, 0);
      peGrad.addColorStop(0, "#be123c");
      peGrad.addColorStop(1, "#e11d48");

      ctx.fillStyle = peGrad;
      ctx.beginPath();
      ctx.roundRect(peX, barY, peBarWidth, barH, [0, 4, 4, 0]);
      ctx.fill();

      // Superimposed Graphical ΔOI% Overlay on Put Bar (outer leading edge)
      const peDelta = st.pe_delta_oi || 0;
      const peDeltaPct = st.pe_delta_oi_pct || 0;
      let peOverlayWidth = 0;

      if (peDelta !== 0 && peBarWidth > 12) {
        const deltaFraction = Math.min(0.45, Math.max(0.08, Math.abs(peDeltaPct) / 100));
        peOverlayWidth = Math.min(peBarWidth * 0.45, Math.max(8, peBarWidth * deltaFraction));
        const overlayX = peX + peBarWidth - peOverlayWidth; // Leading outer edge

        if (peDelta > 0) {
          // Positive ΔOI% (Put Build-up) - Glowing Neon Rose/Coral Overlay
          const overlayGrad = ctx.createLinearGradient(overlayX, 0, overlayX + peOverlayWidth, 0);
          overlayGrad.addColorStop(0, "rgba(251, 113, 133, 0.3)");
          overlayGrad.addColorStop(1, "#fb7185");

          ctx.fillStyle = overlayGrad;
          ctx.beginPath();
          ctx.roundRect(overlayX, barY, peOverlayWidth, barH, [0, 4, 4, 0]);
          ctx.fill();

          ctx.strokeStyle = "rgba(251, 113, 133, 0.9)";
          ctx.lineWidth = 1.5;
          ctx.stroke();
        } else {
          // Negative ΔOI% (Put Unwinding) - Orange/Amber Hatched Strip
          ctx.fillStyle = "rgba(245, 158, 11, 0.5)";
          ctx.beginPath();
          ctx.roundRect(overlayX, barY, peOverlayWidth, barH, [0, 4, 4, 0]);
          ctx.fill();

          ctx.strokeStyle = "rgba(245, 158, 11, 0.9)";
          ctx.lineWidth = 1;
          ctx.stroke();
        }
      }

      // Derivative Build-up State Badge (LB / SB / SC / LU) - Latched to 15-Second Cycle
      const peBuildup = (st.pe_buildup && BUILDUP_CONFIG[st.pe_buildup]) ? BUILDUP_CONFIG[st.pe_buildup] : null;
      if (peBuildup) {
        const tagW = 20;
        const tagH = barH - 4;
        const tagX = (centerX + (centerColWidth / 2)) + 4; // Inner base
        const tagY = barY + 2;

        ctx.fillStyle = peBuildup.bgBadge;
        ctx.strokeStyle = peBuildup.borderColor;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.roundRect(tagX, tagY, tagW, tagH, 3);
        ctx.fill();
        ctx.stroke();

        ctx.fillStyle = peBuildup.textBadge;
        ctx.font = "bold 9px JetBrains Mono, monospace";
        ctx.textAlign = "center";
        ctx.fillText(peBuildup.code, tagX + tagW / 2, tagY + tagH - 3);
      }

      // Superimposed ΔOI% Badge inside Put Bar (pushed inward into solid bar body to prevent overlay obstruction)
      if (peDelta !== 0 && peBarWidth > 58) {
        const isSurge = Math.abs(peDeltaPct) >= 8.0;
        const badgeText = `${peDelta > 0 ? "▲ +" : "▼ "}${peDeltaPct.toFixed(1)}%`;
        ctx.font = "bold 9px JetBrains Mono, monospace";
        const textMetrics = ctx.measureText(badgeText);
        const badgeW = textMetrics.width + 8;
        const badgeH = barH - 4;
        
        // Push badge inward into the solid crimson bar body (to the left of the overlay)
        let badgeX = (peX + peBarWidth - peOverlayWidth) - badgeW - 6;
        const minBadgeX = peX + 28;
        if (badgeX < minBadgeX) badgeX = minBadgeX;

        const badgeY = barY + 2;

        if (badgeX + badgeW < peX + peBarWidth) {
          // Badge Background
          ctx.fillStyle = isSurge ? "rgba(251, 113, 133, 0.45)" : "rgba(0, 0, 0, 0.7)";
          ctx.strokeStyle = isSurge ? "#fb7185" : (peDelta > 0 ? "rgba(244, 63, 94, 0.6)" : "rgba(245, 158, 11, 0.6)");
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.roundRect(badgeX, badgeY, badgeW, badgeH, 3);
          ctx.fill();
          ctx.stroke();

          // Badge Text
          ctx.fillStyle = peDelta > 0 ? "#fecdd3" : "#fbbf24";
          ctx.textAlign = "center";
          ctx.fillText(badgeText, badgeX + badgeW / 2, badgeY + badgeH - 3);
        }
      }

      // Right Bar Label: Put Total OI (in Lakhs, pure number up to 2 decimals)
      const peLakhs = (st.pe_oi / 100000).toFixed(2);
      ctx.fillStyle = "#fecdd3";
      ctx.font = "10.5px JetBrains Mono, monospace";
      ctx.textAlign = "left";
      ctx.fillText(peLakhs, peX + peBarWidth + 6, y + (rowHeight / 2) + 3);

      // Center Column: Strike Box
      const centerBoxX = centerX - (centerColWidth / 2);
      ctx.fillStyle = isATM ? "rgba(245, 158, 11, 0.3)" : "rgba(15, 23, 42, 0.9)";
      ctx.strokeStyle = isATM ? "#f59e0b" : "rgba(255, 255, 255, 0.1)";
      ctx.lineWidth = isATM ? 1.5 : 1;
      ctx.beginPath();
      ctx.roundRect(centerBoxX, barY - 1, centerColWidth, barH + 2, 4);
      ctx.fill();
      ctx.stroke();

      // Strike Text
      ctx.fillStyle = isATM ? "#fbbf24" : "#ffffff";
      ctx.font = isATM ? "bold 11px JetBrains Mono, monospace" : "11px JetBrains Mono, monospace";
      ctx.textAlign = "center";
      ctx.fillText(formatIndianNumber(strike), centerX, y + (rowHeight / 2) + 3);

      // Max Pain Marker Badge
      if (isMaxPain) {
        ctx.fillStyle = "#f59e0b";
        ctx.font = "bold 8px Inter, sans-serif";
        ctx.fillText("PAIN", centerX, y + rowHeight - 2);
      }
    });

    // Center vertical guideline
    ctx.strokeStyle = "rgba(255, 255, 255, 0.12)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(centerX, 0);
    ctx.lineTo(centerX, height);
    ctx.stroke();
  }

  // 2. PCR Session Trend Sparkline
  renderPCRSparkline(canvasId, historyData) {
    const canvas = document.getElementById(canvasId);
    if (!canvas || !historyData || historyData.length < 2) return;

    const ctx = canvas.getContext("2d");
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();

    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);

    const width = rect.width;
    const height = rect.height;
    ctx.clearRect(0, 0, width, height);

    const padTop = 20;
    const padBottom = 24;
    const padLeft = 32;
    const padRight = 16;
    const plotW = width - padLeft - padRight;
    const plotH = height - padTop - padBottom;

    // Determine Y range (clamp between 0.5 and 1.8 min/max)
    let minVal = 0.6;
    let maxVal = 1.4;
    historyData.forEach(h => {
      if (h.total_pcr < minVal) minVal = Math.floor(h.total_pcr * 10) / 10;
      if (h.total_pcr > maxVal) maxVal = Math.ceil(h.total_pcr * 10) / 10;
    });

    const getY = (val) => padTop + plotH - ((val - minVal) / (maxVal - minVal)) * plotH;
    const getX = (idx) => padLeft + (idx / (historyData.length - 1)) * plotW;

    // Reference lines: 1.2 (Bullish), 1.0 (Neutral), 0.8 (Bearish)
    const drawRefLine = (val, color, label) => {
      if (val < minVal || val > maxVal) return;
      const y = getY(val);
      ctx.strokeStyle = color;
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.moveTo(padLeft, y);
      ctx.lineTo(width - padRight, y);
      ctx.stroke();
      ctx.setLineDash([]);

      ctx.fillStyle = color;
      ctx.font = "9px JetBrains Mono, monospace";
      ctx.textAlign = "right";
      ctx.fillText(label, padLeft - 4, y + 3);
    };

    drawRefLine(1.2, "rgba(16, 185, 129, 0.4)", "1.2");
    drawRefLine(1.0, "rgba(255, 255, 255, 0.2)", "1.0");
    drawRefLine(0.8, "rgba(244, 63, 94, 0.4)", "0.8");

    // Draw PCR Trend Line
    ctx.strokeStyle = "#38bdf8";
    ctx.lineWidth = 2.5;
    ctx.beginPath();

    historyData.forEach((h, i) => {
      const x = getX(i);
      const y = getY(h.total_pcr);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();

    // Area Fill
    const lastX = getX(historyData.length - 1);
    const firstX = getX(0);
    ctx.lineTo(lastX, padTop + plotH);
    ctx.lineTo(firstX, padTop + plotH);
    ctx.closePath();
    const areaGrad = ctx.createLinearGradient(0, padTop, 0, padTop + plotH);
    areaGrad.addColorStop(0, "rgba(56, 189, 248, 0.25)");
    areaGrad.addColorStop(1, "rgba(56, 189, 248, 0.0)");
    ctx.fillStyle = areaGrad;
    ctx.fill();

    // Latest Point Dot
    const latest = historyData[historyData.length - 1];
    const latestX = getX(historyData.length - 1);
    const latestY = getY(latest.total_pcr);

    ctx.fillStyle = "#38bdf8";
    ctx.beginPath();
    ctx.arc(latestX, latestY, 4, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = "#ffffff";
    ctx.lineWidth = 1.5;
    ctx.stroke();

    // Time labels
    ctx.fillStyle = "#64748b";
    ctx.font = "9px JetBrains Mono, monospace";
    ctx.textAlign = "left";
    ctx.fillText(historyData[0].time_str || "", padLeft, height - 6);
    ctx.textAlign = "right";
    ctx.fillText(latest.time_str || "", width - padRight, height - 6);
  }

  // 3. IV Skew Curve Chart
  renderIVSkewChart(canvasId, ivSkewData, spotPrice) {
    const canvas = document.getElementById(canvasId);
    if (!canvas || !ivSkewData || !ivSkewData.curve) return;

    const ctx = canvas.getContext("2d");
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();

    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);

    const width = rect.width;
    const height = rect.height;
    ctx.clearRect(0, 0, width, height);

    const curve = ivSkewData.curve;
    if (curve.length < 2) return;

    const padTop = 18;
    const padBottom = 22;
    const padLeft = 32;
    const padRight = 16;
    const plotW = width - padLeft - padRight;
    const plotH = height - padTop - padBottom;

    // Find min and max IV
    let minIV = 5.0;
    let maxIV = 30.0;
    curve.forEach(c => {
      if (c.ce_iv > 0 && c.ce_iv < minIV) minIV = Math.floor(c.ce_iv);
      if (c.pe_iv > 0 && c.pe_iv < minIV) minIV = Math.floor(c.pe_iv);
      if (c.ce_iv > maxIV) maxIV = Math.ceil(c.ce_iv);
      if (c.pe_iv > maxIV) maxIV = Math.ceil(c.pe_iv);
    });

    const getY = (iv) => padTop + plotH - ((iv - minIV) / (maxIV - minIV)) * plotH;
    const getX = (idx) => padLeft + (idx / (curve.length - 1)) * plotW;

    // Y Axis Guidelines
    [minIV, Math.round((minIV + maxIV) / 2), maxIV].forEach(val => {
      const y = getY(val);
      ctx.strokeStyle = "rgba(255, 255, 255, 0.06)";
      ctx.beginPath();
      ctx.moveTo(padLeft, y);
      ctx.lineTo(width - padRight, y);
      ctx.stroke();

      ctx.fillStyle = "#64748b";
      ctx.font = "9px JetBrains Mono, monospace";
      ctx.textAlign = "right";
      ctx.fillText(`${val}%`, padLeft - 4, y + 3);
    });

    // Call IV Curve (Emerald)
    ctx.strokeStyle = "#10b981";
    ctx.lineWidth = 2;
    ctx.beginPath();
    curve.forEach((pt, i) => {
      const x = getX(i);
      const y = getY(pt.ce_iv);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();

    // Put IV Curve (Rose)
    ctx.strokeStyle = "#f43f5e";
    ctx.lineWidth = 2;
    ctx.beginPath();
    curve.forEach((pt, i) => {
      const x = getX(i);
      const y = getY(pt.pe_iv);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();

    // Strike Labels (start, middle, end)
    ctx.fillStyle = "#94a3b8";
    ctx.font = "9px JetBrains Mono, monospace";
    ctx.textAlign = "left";
    ctx.fillText(curve[0].strike.toString(), padLeft, height - 6);
    ctx.textAlign = "center";
    ctx.fillText(curve[Math.floor(curve.length / 2)].strike.toString(), padLeft + plotW / 2, height - 6);
    ctx.textAlign = "right";
    ctx.fillText(curve[curve.length - 1].strike.toString(), width - padRight, height - 6);
  }
}

window.optionCharts = new OptionChainCharts();
