# FTMO trading system

A ground-up algorithmic forex trading system targeting the FTMO $10k
Standard challenge. Python + MetaTrader5.

## Architecture

```
config/          FTMO rules + settings — single source of truth   [DONE]
risk/            Position sizing + FTMO rule enforcement          [DONE — 7/7 tests passing]
data/            MT5 connection, symbol info, OHLC/tick fetching  [DONE — 8/8 tests passing]
strategy/        Signal generation (pure, no risk/execution)      [DONE — 5/5 tests passing, example only]
execution/       Live + backtest order execution                 [not yet built]
validation/      Walkforward, Monte Carlo, performance stats      [not yet built]
orchestration/   Main loop, logging, alerts, kill switch          [not yet built]
tests/           Sanity + unit tests
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

**Important — not yet resolved:** bar timestamps come back in MT5
*server time*, not UTC, and this isn't converted yet. Before building
any session-boundary-sensitive logic (e.g. "London open"), we need to
pin down your broker's server UTC offset and DST behavior.

**Untested against the real terminal.** Everything above is verified
against a fake MT5 module in this sandbox (no real terminal available
here). Run `python -m tests.test_data_layer` here for logic
correctness, but do a manual smoke test on your machine — connect for
real and fetch a few bars — before building strategy logic on top of it.

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

## Strategy layer notes

- `strategy/base.py` — the `Strategy` interface every strategy
  implements: `generate_signal(ohlc_df) -> Signal`. Knows nothing about
  account size, risk, or execution — same class runs unchanged in
  backtest and live.
- `strategy/sma_crossover_example.py` — a working example (SMA
  crossover) that proves the interface end-to-end. **This is a
  template, not a recommendation** — it's a well-known, generally
  weak strategy on its own. Your actual trading hypothesis goes in a
  new file implementing the same `Strategy` interface.

## Next step

Decide on and implement your real trading hypothesis as a `Strategy`
subclass, then build `execution/` (live + backtest executors sharing
one interface) so we can actually run it against history.

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
