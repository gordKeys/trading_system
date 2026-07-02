# FTMO trading system

A ground-up algorithmic forex trading system targeting the FTMO $10k
Standard challenge. Python + MetaTrader5.

## Architecture

```
config/          FTMO rules + settings — single source of truth   [DONE]
risk/            Position sizing + FTMO rule enforcement          [DONE — 7 tests]
data/            MT5 connection, symbol info, OHLC/tick fetching  [DONE — 8 tests, live-verified]
strategy/        Multiple candidate strategies                    [DONE — see below]
execution/       Backtest executor (live executor not yet built)  [DONE — 5 tests]
validation/      Metrics + leaderboard comparing all strategies   [DONE — 4 tests]
orchestration/   Main loop, logging, alerts, kill switch          [not yet built]
tests/           49 tests total, all passing
```

## Data layer notes

- `data/mt5_connector.py` — connection lifecycle. Accepts the `mt5`
  module as a constructor argument so it's testable without a real
  MT5 terminal (tests inject a fake; production leaves it blank and
  it lazily imports the real `MetaTrader5` package).
- `data/symbol_info.py` — pulls pip size/value per symbol from MT5 at
  runtime rather than hardcoding it (this varies by symbol and
  account currency — hardcoding it for EURUSD would silently be wrong
  for USDJPY or a CFD).
- `data/market_data.py` — OHLC + tick fetching, returns pandas
  DataFrames with a fixed column schema so strategy code never needs
  to know it's talking to MT5 specifically.

**Resolved:** broker server clock measured at **UTC+3** on 2026-07-02
(`check_server_offset.py`), consistent with EET summer time. This will
almost certainly shift to **UTC+2** around late October when EU DST
ends. `config/settings.py::BrokerServerClock` holds this value —
**re-run `check_server_offset.py` after DST transitions and update it.**
`data/broker_time.py` provides `broker_time_to_utc()` /
`utc_to_broker_time()` for any strategy logic that needs real-world
session boundaries (London open, NY open, etc.).

**Bug fixed:** `fetch_latest_tick` originally used
`datetime.fromtimestamp()`, which silently applied the local machine's
timezone on top of the MT5 epoch — causing tick time to disagree with
bar time by whatever offset the running machine happened to be set to
(showed up as a 2-hour drift on the VPS). Fixed to decode the same way
as bar timestamps; a regression test guards against this recurring.

**Second bug fixed (found via real multi-pair leaderboard results):**
the multi-pair leaderboard correctly passed each pair's real pip size
into the backtest engine's position sizing, but never passed it into
the STRATEGIES themselves — which use it to convert `stop_pips` into a
real price distance. Every strategy defaulted to `pip_size=0.0001`
regardless of pair, ~100x too tight for JPY pairs (real pip size 0.01).
This made every single strategy look catastrophic specifically on
USDJPY — an artifact of the bug, not a real finding about that pair.
Fixed in `validation/leaderboard.py::build_strategies()`; a regression
test (`tests/test_leaderboard_pip_size.py`) proves a JPY-configured
strategy produces a stop distance ~100x wider than a EUR-configured
one, so this can't silently regress.

**Reading multi-pair results correctly:** a result near **-8% paired
with a large blocked-signal count is not "weak performance" — it means
the strategy blew through the drawdown safety buffer (80% of FTMO's
10% limit) partway through the test and got locked out of trading for
the rest of it.** In real terms that's the FTMO challenge ending in
failure, not a bad month. Always check the blocked count alongside
return% before concluding anything from these tables.

**Verified against the real terminal.** MT5 connection, symbol info,
OHLC/tick fetching, and the server-time offset have all been confirmed
against a live demo account on the VPS.

## Design principles

1. **FTMO rules are config, not code.** `config/ftmo_rules.py` is the
   only place account limits are defined. Nothing else hardcodes a
   percentage.
2. **The risk layer knows nothing about strategy logic.** It only ever
   answers "can I trade right now?" and "how big should this trade
   be?" — testable in complete isolation from any strategy.
3. **Internal safety buffers sit inside FTMO's real limits.** The bot
   stops itself at 80% of FTMO's actual daily loss / drawdown limits
   by default (see `config/settings.py::SafetyBuffers`), so slippage
   or a fast market move can't blow through the real limit before the
   bot reacts.
4. **Live and backtest execution will share one interface.** This is
   what makes the backtest trustworthy — strategy and risk code never
   know which one they're running against.

## Confirmed FTMO account details (from you, verify against dashboard before going live)

- FTMO Standard, $10k
- Profit target: 10% (Phase 1), 5% (Phase 2)
- Max daily loss: 5%, Max total drawdown: 10%
- Drawdown anchor: **static** from initial balance (not trailing)

## Setup

```bash
pip install -r requirements.txt
```

Create a `.env` file (do NOT commit this) with your MT5 demo credentials:

```
MT5_LOGIN=12345678
MT5_PASSWORD=your_password
MT5_SERVER=YourBroker-Demo
```

## Run tests

```bash
python -m tests.test_risk_manager
```

## Strategy candidates

Five strategies now implement the `Strategy` interface, all runnable
through the same backtest/leaderboard pipeline:

| Strategy | File | Hypothesis |
|---|---|---|
| `sma_crossover_example` | `strategy/sma_crossover_example.py` | Template only — not a real candidate |
| `orb_breakout` | `strategy/orb_breakout.py` | Opening-range breakout at session start |
| `trend_following_ma` | `strategy/trend_following_ma.py` | MA crossover confirmed by slope (filters whipsaws) |
| `mean_reversion_rsi` | `strategy/mean_reversion_rsi.py` | RSI extreme reversal (no trend filter — will lose in strong trends by design) |
| `combo_trend_confirmed_breakout` | `strategy/combo_trend_breakout.py` | ORB breakout, taken only when it agrees with the broader trend |

**Note on statefulness:** `orb_breakout` and the combo strategy track
per-day state (has this session already been traded) as instance
state — a deliberate, documented exception to the "pure" guidance in
`strategy/base.py`. Always construct a fresh instance per backtest run.

## Backtest engine

`execution/backtest_executor.py` replays a strategy bar-by-bar through
the REAL `RiskManager` — not a simplified stand-in. Documented
simplifications: single position at a time, fills at the signal's
exact entry price (no slippage/spread modeling yet), and if a single
bar's range touches both stop and take-profit, the stop is
conservatively assumed to have triggered first.

## Leaderboard — comparing strategies

```bash
python -m validation.leaderboard --csv path/to/EURUSD_M15.csv
```

Ranks every strategy on the same historical data by total return, and
also reports win rate, max drawdown, profit factor, and how many
signals the risk manager blocked.

**Getting real historical data from your VPS:**
```python
from data.mt5_connector import MT5Connector
from data.market_data import fetch_ohlc, Timeframe

with MT5Connector() as conn:
    df = fetch_ohlc(conn, "EURUSD", Timeframe.M15, count=5000)
    df.to_csv("EURUSD_M15.csv")
```
Then copy that CSV here and run the leaderboard against it.

**Without `--csv`**, the leaderboard runs against synthetic random-walk
data — this only proves the pipeline doesn't crash. It tells you
NOTHING about which strategy is actually good (random walks have no
real trend, breakout, or mean-reversion structure). Never use those
numbers to pick a strategy.

## Getting more data and testing across pairs

**1. Export more history across multiple pairs** — run on the VPS:
```powershell
python export_data.py
```
Edit `SYMBOLS` and `BAR_COUNT` at the top of that file first. Produces
`data_export/<SYMBOL>_M15.csv` + `<SYMBOL>_meta.json` (pip size/value)
per symbol. Note: MT5 may cap how many bars `copy_rates_from_pos`
returns per call depending on your broker's history settings — if you
get fewer bars than requested, that's a broker-side limit, not a bug.

**2. Run the multi-pair leaderboard:**
```powershell
python -m validation.multi_pair_leaderboard --dir data_export
```
Prints the full metrics table per pair, then a summary matrix
(strategy × pair → return %) and calls out the best-performing
strategy on each pair — this is what surfaces "combos," e.g. if
`combo_trend_confirmed_breakout` does best on EURUSD but
`mean_reversion_rsi` does best on a range-bound pair like AUDUSD, that
tells you these might warrant different treatment per instrument
rather than picking one strategy for everything.

## Segmented (walkforward-style) validation

```bash
python -m validation.walkforward --csv data_export/USDJPY_M15.csv --strategy trend_following_ma --pip-size 0.01 --pip-value 6.21 --segments 5
```

Splits the historical data into N sequential, non-overlapping periods
and runs the strategy independently on each (fresh instance, fresh
$10k account per segment — no state or capital carries over). Answers
a different question than the leaderboard: not "is this profitable
overall" but "is it CONSISTENTLY profitable, or did the aggregate
number come from one lucky stretch."

**What this is NOT:** we have no parameter optimizer yet, so this
doesn't re-fit parameters per segment — it's fixed-parameter,
segmented out-of-sample testing, not full walkforward-with-
reoptimization. Still the right next step before trusting any
strategy's aggregate leaderboard number.

Available `--strategy` names: `sma_crossover_example`, `orb_breakout`,
`trend_following_ma`, `mean_reversion_rsi`, `combo_trend_confirmed_breakout`.

## What the leaderboard does NOT yet tell you

A single backtest run on one historical window is step one, not the
final word — before trusting any result enough to trade it:
- **Walkforward validation** — optimize on one period, test on the
  next unseen one. Not built yet.
- **Multiple market regimes** — trending vs ranging vs volatile
  periods. A strategy that wins on 2026 H1 data might fail elsewhere.
- **Realistic costs** — spread and slippage aren't modeled yet, which
  matters most for the higher-frequency strategies (RSI mean-reversion
  fired the most signals in early testing).
- **Parameter sensitivity** — is the result robust to small parameter
  changes, or a lucky fit to this exact config?

## Next step

Pull real historical data from your VPS (see above) and run the
leaderboard against it to get a real (not synthetic) ranking. Once we
have real numbers, decide whether to refine the leading strategy,
build walkforward validation, or start on the live executor.

## Git / GitHub

See the conversation for a full walkthrough — short version:

```bash
cd trading_system
git init
git add .
git commit -m "Initial commit: config, risk, data, strategy layers"
git branch -M main
git remote add origin https://github.com/<your-username>/<repo-name>.git
git push -u origin main
```

`.gitignore` is already set up to exclude `.env` (your MT5 credentials),
`__pycache__`, and virtual environments — never remove `.env` from it.
