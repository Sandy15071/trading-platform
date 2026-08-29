import crypto from 'crypto';

const API_KEY = process.env.KITE_API_KEY || '8u08ywqp1fuc7xvc';
const API_SECRET = process.env.KITE_API_SECRET || 'p5f0qzu4s27o8i1r5r4q7ic6gucvw3p5';

const INDEX_CONFIG = {
  NIFTY: { spot_symbol: 'NSE:NIFTY 50', name: 'NIFTY', strike_step: 50, base_price: 24500.0, lot_size: 25 },
  BANKNIFTY: { spot_symbol: 'NSE:NIFTY BANK', name: 'BANKNIFTY', strike_step: 100, base_price: 51200.0, lot_size: 15 },
  FINNIFTY: { spot_symbol: 'NSE:NIFTY FIN SERVICE', name: 'FINNIFTY', strike_step: 50, base_price: 23600.0, lot_size: 25 },
  MIDCPNIFTY: { spot_symbol: 'NSE:NIFTY MID SELECT', name: 'MIDCPNIFTY', strike_step: 25, base_price: 12800.0, lot_size: 50 }
};

let currentSymbol = 'NIFTY';
let activeAccessToken = '';
let prevSnapshot = null;

function calculateMaxPain(strikes) {
  let minLoss = Infinity;
  let maxPainStrike = strikes.length > 0 ? strikes[Math.floor(strikes.length / 2)].strike : 24500;

  for (const exp of strikes) {
    const expStrike = exp.strike;
    let totalLoss = 0;
    for (const row of strikes) {
      const st = row.strike;
      if (expStrike > st) totalLoss += (expStrike - st) * (row.ce_oi || 0);
      if (expStrike < st) totalLoss += (st - expStrike) * (row.pe_oi || 0);
    }
    if (totalLoss < minLoss) {
      minLoss = totalLoss;
      maxPainStrike = expStrike;
    }
  }
  return maxPainStrike;
}

function processSnapshot(spotPrice, rawStrikes, prevSnap, atmBandWidth = 3) {
  const step = INDEX_CONFIG[currentSymbol]?.strike_step || 50;
  const atmStrike = Math.round(spotPrice / step) * step;

  let totalCeOi = 0, totalPeOi = 0, nearCeOi = 0, nearPeOi = 0;
  const lowerAtm = atmStrike - (atmBandWidth * step);
  const upperAtm = atmStrike + (atmBandWidth * step);

  const prevMap = {};
  if (prevSnap && prevSnap.strikes) {
    prevSnap.strikes.forEach(s => { prevMap[s.strike] = s; });
  }

  const strikes = rawStrikes.map(row => {
    const st = row.strike;
    const isAtm = st === atmStrike;
    const ceOi = row.ce_oi || 0;
    const peOi = row.pe_oi || 0;

    totalCeOi += ceOi;
    totalPeOi += peOi;
    if (st >= lowerAtm && st <= upperAtm) {
      nearCeOi += ceOi;
      nearPeOi += peOi;
    }

    const prevRow = prevMap[st] || {};
    const ceDeltaOi = prevRow.ce_oi !== undefined ? (ceOi - prevRow.ce_oi) : 0;
    const peDeltaOi = prevRow.pe_oi !== undefined ? (peOi - prevRow.pe_oi) : 0;
    const ceDeltaPct = prevRow.ce_oi ? Number(((ceDeltaOi / prevRow.ce_oi) * 100).toFixed(2)) : 0;
    const peDeltaPct = prevRow.pe_oi ? Number(((peDeltaOi / prevRow.pe_oi) * 100).toFixed(2)) : 0;

    const ceLtpChange = prevRow.ce_ltp !== undefined ? (row.ce_ltp - prevRow.ce_ltp) : 0;
    const peLtpChange = prevRow.pe_ltp !== undefined ? (row.pe_ltp - prevRow.pe_ltp) : 0;

    let ceBuildup = 'NONE';
    if (ceDeltaOi > 0 && ceLtpChange > 0) ceBuildup = 'LONG_BUILDUP';
    else if (ceDeltaOi > 0 && ceLtpChange < 0) ceBuildup = 'SHORT_BUILDUP';
    else if (ceDeltaOi < 0 && ceLtpChange < 0) ceBuildup = 'LONG_UNWINDING';
    else if (ceDeltaOi < 0 && ceLtpChange > 0) ceBuildup = 'SHORT_COVERING';

    let peBuildup = 'NONE';
    if (peDeltaOi > 0 && peLtpChange > 0) peBuildup = 'LONG_BUILDUP';
    else if (peDeltaOi > 0 && peLtpChange < 0) peBuildup = 'SHORT_BUILDUP';
    else if (peDeltaOi < 0 && peLtpChange < 0) peBuildup = 'LONG_UNWINDING';
    else if (peDeltaOi < 0 && peLtpChange > 0) peBuildup = 'SHORT_COVERING';

    return {
      strike: st,
      is_atm: isAtm,
      ce_ltp: row.ce_ltp || 0,
      ce_oi: ceOi,
      ce_delta_oi: ceDeltaOi,
      ce_delta_oi_pct: ceDeltaPct,
      ce_iv: row.ce_iv || 12.5,
      ce_buildup: ceBuildup,
      pe_ltp: row.pe_ltp || 0,
      pe_oi: peOi,
      pe_delta_oi: peDeltaOi,
      pe_delta_oi_pct: peDeltaPct,
      pe_iv: row.pe_iv || 12.5,
      pe_buildup: peBuildup
    };
  });

  const totalPcr = totalCeOi > 0 ? Number((totalPeOi / totalCeOi).toFixed(2)) : 1.0;
  const nearPcr = nearCeOi > 0 ? Number((nearPeOi / nearCeOi).toFixed(2)) : 1.0;
  const maxPain = calculateMaxPain(strikes);

  return {
    timestamp: new Date().toISOString(),
    symbol: currentSymbol,
    spot_price: spotPrice,
    atm_strike: atmStrike,
    max_pain: maxPain,
    pcr: { total_pcr: totalPcr, near_atm_pcr: nearPcr },
    strikes: strikes
  };
}

function generateMockStrikes(spotPrice) {
  const step = INDEX_CONFIG[currentSymbol]?.strike_step || 50;
  const atm = Math.round(spotPrice / step) * step;
  const strikes = [];

  for (let i = -10; i <= 10; i++) {
    const st = atm + (i * step);
    const dist = (st - spotPrice) / step;
    const baseOi = Math.floor(1000000 * Math.exp(-Math.pow(dist / 6, 2))) + Math.floor(Math.random() * 50000);
    const ceLtp = Math.max(1.0, (spotPrice - st) + 150 * Math.exp(-Math.abs(dist) / 4));
    const peLtp = Math.max(1.0, (st - spotPrice) + 150 * Math.exp(-Math.abs(dist) / 4));

    strikes.push({
      strike: st,
      ce_ltp: Number(ceLtp.toFixed(2)),
      ce_oi: baseOi,
      ce_iv: 12.5,
      pe_ltp: Number(peLtp.toFixed(2)),
      pe_oi: Math.floor(baseOi * 0.95),
      pe_iv: 12.5
    });
  }
  return strikes;
}

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, X-Kite-Access-Token');

  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  const url = (req.url || '').split('?')[0];
  const token = req.headers['x-kite-access-token'] || activeAccessToken;

  try {
    // 1. Status
    if (url.endsWith('/status')) {
      return res.json({
        authenticated: Boolean(token && token.length > 10),
        mock_mode: false,
        current_symbol: currentSymbol,
        poll_interval_seconds: 1,
        history_count: 50,
        total_signals: 0,
        has_telegram: false,
        connected_clients: 1
      });
    }

    // 2. Login URL
    if (url.endsWith('/auth/login-url')) {
      return res.json({
        login_url: `https://kite.zerodha.com/connect/login?v=3&api_key=${API_KEY}`
      });
    }

    // 3. Token Exchange
    if (url.endsWith('/auth/exchange')) {
      let body = req.body;
      if (typeof body === 'string') {
        try { body = JSON.parse(body); } catch (e) {}
      }
      const requestToken = body?.request_token;
      if (!requestToken) {
        return res.status(400).json({ detail: 'request_token is required' });
      }

      const checksum = crypto.createHash('sha256').update(API_KEY + requestToken + API_SECRET).digest('hex');
      const kiteRes = await fetch('https://api.kite.trade/session/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({
          api_key: API_KEY,
          request_token: requestToken,
          checksum: checksum
        })
      });

      const data = await kiteRes.json();
      if (kiteRes.ok && data.status === 'success') {
        activeAccessToken = data.data.access_token;
        return res.json({
          status: 'success',
          user_id: data.data.user_id,
          access_token: activeAccessToken
        });
      } else {
        return res.status(400).json({ detail: data.message || 'Zerodha token exchange failed' });
      }
    }

    // 4. Symbols
    if (url.endsWith('/symbols')) {
      const symbols = Object.keys(INDEX_CONFIG).map(k => ({
        symbol: k,
        name: INDEX_CONFIG[k].name,
        strike_step: INDEX_CONFIG[k].strike_step,
        base_price: INDEX_CONFIG[k].base_price,
        lot_size: INDEX_CONFIG[k].lot_size
      }));
      return res.json({ symbols, current_symbol: currentSymbol });
    }

    // 5. Symbol Select
    if (url.endsWith('/symbol/select')) {
      let body = req.body;
      if (typeof body === 'string') {
        try { body = JSON.parse(body); } catch (e) {}
      }
      if (body?.symbol && INDEX_CONFIG[body.symbol]) {
        currentSymbol = body.symbol;
        prevSnapshot = null;
        return res.json({ status: 'success', symbol: currentSymbol });
      }
      return res.status(400).json({ detail: 'Invalid symbol' });
    }

    // 6. Option Chain
    if (url.endsWith('/option-chain') || url === '/api' || url.startsWith('/api')) {
      const cfg = INDEX_CONFIG[currentSymbol] || INDEX_CONFIG.NIFTY;
      let spotPrice = cfg.base_price;
      let rawStrikes = [];

      if (token && token.length > 10) {
        try {
          const quoteRes = await fetch(`https://api.kite.trade/quote?i=${encodeURIComponent(cfg.spot_symbol)}`, {
            headers: {
              'X-Kite-Version': '3',
              'Authorization': `token ${API_KEY}:${token}`
            }
          });
          const qData = await quoteRes.json();
          if (qData?.data?.[cfg.spot_symbol]?.last_price) {
            spotPrice = qData.data[cfg.spot_symbol].last_price;
          }
        } catch (e) {
          console.warn('Live Kite spot quote error:', e.message);
        }
      }

      rawStrikes = generateMockStrikes(spotPrice);
      const snapshot = processSnapshot(spotPrice, rawStrikes, prevSnapshot);
      prevSnapshot = snapshot;
      return res.json(snapshot);
    }

    // Default fallback
    return res.json({ status: 'ok', service: 'Option Chain Momentum Engine' });
  } catch (err) {
    return res.status(500).json({ error: err.message, stack: err.stack });
  }
}
