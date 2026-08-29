# Product Requirements Document
## Option Chain Momentum Indicator (Zerodha Kite Connect)

| | |
|---|---|
| **Doc status** | Draft v1.0 |
| **Owner** | You (product owner / sole developer) |
| **Target build tool** | Google Antigravity IDE |
| **Data source** | Zerodha Kite Connect API |

---

## 1. Summary

A standalone, single-screen desktop/local-web dashboard that reads live
option chain data from Zerodha Kite Connect for a chosen underlying
(e.g. NIFTY, BANKNIFTY), computes a set of option-chain-derived analytics
(OI, Change in OI, PCR, Max Pain, IV), visualizes them graphically, and
runs a rule-based momentum engine that alerts the user across four
channels when specific option-premium momentum patterns occur.

This is **not** a trading platform. It has no price candlestick chart, no
order placement, and no portfolio/positions tracking. It is a single-purpose
analytical indicator.

## 2. Problem statement

Retail traders using Kite have access to a raw option chain table but no
built-in way to (a) see OI/PCR/Max Pain/IV trends visualized at a glance,
or (b) get proactively alerted when the data shifts in a way that signals
momentum, without manually watching the table. Kite's own app does not
support injecting custom indicators or third-party overlays into its
interface, so this must be a separate, standalone screen.

## 3. Goals

- G1: Surface option-chain analytics (OI, ΔOI, PCR, Max Pain, IV) for ATM
  ± 10 strikes, both Call and Put, refreshed every 15–30 seconds.
- G2: Visualize this data graphically in a way that's faster to read than
  the raw table.
- G3: Detect and alert on defined momentum patterns automatically, across
  on-screen, desktop/browser, audible, and Telegram channels simultaneously.
- G4: Keep the system a lightweight, single-symbol, single-screen tool —
  resist scope creep toward a full platform.

## 4. Non-goals (explicitly out of scope for v1)

- Price candlestick/line charting of the underlying
- Order placement or execution of any kind
- Portfolio, positions, or P&L tracking
- Multi-symbol simultaneous dashboards
- Mobile app (browser-based desktop use only for v1)
- Backtesting of the momentum rules against historical data (may be a
  future phase, not v1)

## 5. Target user

Just the one user (you), an active options trader with an existing
Zerodha account and Kite Connect subscription, who wants a passive
monitoring/alerting tool running in a browser tab alongside the Kite app,
not a replacement for it.

## 6. Data source & constraints

- **Provider:** Zerodha Kite Connect (paid plan, ~₹500/month), which
  provides REST APIs for quotes/option chain data and WebSocket for tick
  streaming.
- **Auth model:** Daily login flow — browser-based login generates a
  request token, exchanged for an access token that expires every day.
  This is a hard constraint of Kite Connect, not a design choice; the
  system must handle re-authentication each trading day.
- **Fetch method:** REST polling, not WebSocket. Option chain OI/IV data
  does not need tick-level streaming; a 15–30 second poll interval is the
  target cadence and should stay comfortably within Kite's rate limits.
- **Computation ownership:** Kite Connect returns raw quote/OI/IV data
  only. All derived analytics (PCR, Max Pain, IV skew, momentum detection)
  must be computed within this application — Kite does not provide them.

## 7. Functional requirements

### 7.1 Symbol selection
- FR-1: User can select one underlying symbol at a time from a dropdown
  (e.g. NIFTY, BANKNIFTY, or any F&O symbol available via Kite).

### 7.2 Option chain data fetch
- FR-2: On each poll cycle, fetch quote data for ATM plus 10 strikes ITM
  and 10 strikes OTM on both Call and Put sides (21 strikes per side).
- FR-3: For each strike/side, capture: OI, LTP, IV. Compute ΔOI as the
  difference from the previous poll cycle (not from session open, unless
  both are shown).
- FR-4: Maintain a rolling history buffer (last 30–60 cycles minimum,
  configurable) of per-strike OI, session PCR, and Max Pain, so the
  momentum engine can compare against recent trend, not just the latest
  snapshot.

### 7.3 Derived analytics
- FR-5: Compute PCR as Put OI ÷ Call OI, both (a) across the full fetched
  strike range and (b) for a tighter near-ATM band (e.g. ATM ± 3 strikes).
- FR-6: Compute Max Pain each cycle using the standard algorithm: for each
  candidate strike, sum intrinsic-value payout obligations across all
  strikes' OI, and select the strike that minimizes total payout.
- FR-7: Compute IV skew shape across the fetched strike range (to visualize
  whether OTM puts or OTM calls are pricing in more relative premium).

### 7.4 Visualization
- FR-8: Display a side-by-side OI bar view per strike (Call bars one
  direction, Put bars the other), across ATM ± 10.
- FR-9: Display a PCR trend sparkline across the session's polled history.
- FR-10: Display an IV skew curve across the strike range.
- FR-11: Mark the current Max Pain strike clearly against the strike axis.
- FR-12: Display a running feed/log of the most recent momentum signals
  (timestamp, strike, side, rule type, message), most recent first.

### 7.5 Momentum rule engine
- FR-13: **OI surge** — flag when a strike's ΔOI in one cycle exceeds a
  configurable percentage of its existing OI (default suggestion: 8–10%).
  Signal must specify strike, side, and direction (build-up vs unwinding).
- FR-14: **PCR threshold cross** — flag when PCR crosses a configurable
  band (default suggestion: >1.2 bullish-leaning, <0.8 bearish-leaning),
  or moves more than a configurable delta between consecutive cycles.
- FR-15: **Max Pain drift** — flag when the Max Pain strike changes from
  the previous cycle; specifically note whether it moved toward or away
  from current spot price.
- FR-16: **IV spike** — flag when a strike's IV jumps beyond a configurable
  relative threshold (default suggestion: >15%) versus its own recent
  rolling average.
- FR-17: **ATM OI imbalance** — flag a strong one-sided OI build directly
  at/near ATM on either side beyond a configurable ratio.
- FR-18: All thresholds in FR-13 through FR-17 must be user-configurable
  (config file or in-app settings panel), not hardcoded — thresholds will
  need tuning after observing live behavior.
- FR-19: Each fired signal produces a structured object with at minimum:
  timestamp, strike, side, rule type, strength/severity, human-readable
  message.

### 7.6 Notifications
- FR-20: Every fired signal triggers all four channels simultaneously:
  1. **On-screen** — highlight the affected row/strike in the table and
     flash the corresponding bar in the graphic.
  2. **Desktop/browser push** — via the Web Notifications API, surfacing
     even when the browser tab is unfocused (requires one-time permission
     grant).
  3. **Audible alert** — a short beep via Web Audio API.
  4. **Telegram** — message sent via a Telegram bot (`sendMessage` call),
     using a bot token and chat ID the user provides as configuration.

### 7.7 Configuration & secrets
- FR-21: Kite API key/secret, Kite access token, and Telegram bot
  token/chat ID must be stored as environment variables or in a local,
  git-ignored `.env` file — never hardcoded in source.
- FR-22: Rule thresholds and poll interval must be adjustable without
  code changes (config file or settings UI).

## 8. Non-functional requirements

- NFR-1: Single local process; no external hosting/deployment required
  for v1.
- NFR-2: Poll interval configurable within a 15–30 second default range;
  must not exceed Kite Connect's REST rate limits.
- NFR-3: Daily re-authentication flow must be straightforward to run each
  trading morning (a script or one-click login is acceptable for v1; full
  automation of the login step is a nice-to-have, not a requirement).
- NFR-4: Rolling history buffer can be in-memory for v1 (no persistent
  database required), but should not be lost on a simple page refresh if
  reasonably avoidable (e.g. keep state in the backend process, not just
  browser memory).
- NFR-5: No trading account credentials or order-placement scopes should
  be requested from Kite Connect beyond what's needed for market-quote
  read access.

## 9. Success criteria

- SC-1: Dashboard correctly displays OI/ΔOI/IV for ATM ± 10 strikes on
  both sides, refreshed every 15–30 seconds, matching what's visible in
  the Kite app's own option chain for the same symbol/moment (sanity
  check).
- SC-2: PCR and Max Pain values computed by the app match manual
  calculation from the same raw data (spot-check against a manual
  calculation at least once during development).
- SC-3: At least one momentum rule fires correctly against a known/staged
  data pattern during testing (can be tested with mocked data before going
  live).
- SC-4: All four notification channels fire together within a few seconds
  of a signal being generated.
- SC-5: Thresholds can be changed without touching code and take effect on
  the next poll cycle.

## 10. Suggested build sequence

1. Kite Connect auth flow (manual daily login acceptable for v1)
2. Option chain REST fetch for a chosen symbol, ATM ± 10 strikes both sides
3. Derived metrics (PCR, Max Pain, IV skew) — validate against Kite's own
   option chain view for correctness
4. Rolling history buffer (in-memory) + momentum rule engine
5. Local web dashboard: table + OI bar graphic + PCR sparkline + signal
   feed
6. Notification channels, in order of implementation ease: on-screen →
   browser push → sound → Telegram
7. Configuration panel/file for rule thresholds and poll interval

## 11. Open questions / decisions to confirm during build

- Exact default thresholds for each momentum rule (starting values
  suggested above; expect to tune after live observation).
- Whether Max Pain/PCR near-ATM band should be configurable in width
  (default suggestion: ATM ± 3) or fixed.
- Whether daily Kite login should be a manual script run each morning or
  a more automated flow (automation adds complexity and has security
  trade-offs worth discussing before building).

## 12. Constraints & dependencies

- Requires an active Zerodha trading account and a paid Kite Connect
  subscription (~₹500/month) plus an API key created at
  developers.kite.trade.
- Requires a Telegram bot (created via BotFather) for the Telegram
  notification channel.
- Kite Connect access tokens expire daily — this is an external constraint,
  not something the build can eliminate, only streamline.
