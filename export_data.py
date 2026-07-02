"""
Export historical OHLC data (and symbol metadata) for multiple pairs
at once — run this on the VPS with MT5 open and logged in.

Usage:
    python export_data.py

Edit SYMBOLS and BAR_COUNT below as needed. Produces, per symbol:
  - data_export/<SYMBOL>_M15.csv       (OHLC history)
  - data_export/<SYMBOL>_meta.json     (pip_size, pip_value_per_lot — needed
                                         by the leaderboard to size positions
                                         correctly per pair)

MT5's copy_rates_from_pos caps out around 5000-10000 bars per call
depending on your broker/terminal history settings — if BAR_COUNT
returns fewer bars than requested, that's a broker-side history limit,
not a bug here. For more history than that, you'd need copy_rates_range
with a wider date span, or fetch in successive chunks (not implemented
here — ask if you want this extended).
"""

import json
import os

from data.mt5_connector import MT5Connector
from data.market_data import fetch_ohlc, Timeframe
from data.symbol_info import get_symbol_info

SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD"]
TIMEFRAME = Timeframe.M15
BAR_COUNT = 20_000  # ask your broker for max available if this comes back short
OUTPUT_DIR = "data_export"

os.makedirs(OUTPUT_DIR, exist_ok=True)

with MT5Connector() as conn:
    for symbol in SYMBOLS:
        print(f"Fetching {symbol}...")
        try:
            df = fetch_ohlc(conn, symbol, TIMEFRAME, count=BAR_COUNT)
            info = get_symbol_info(conn, symbol)
        except Exception as e:
            print(f"  SKIPPED {symbol}: {e}")
            continue

        csv_path = os.path.join(OUTPUT_DIR, f"{symbol}_M15.csv")
        df.to_csv(csv_path)

        meta_path = os.path.join(OUTPUT_DIR, f"{symbol}_meta.json")
        with open(meta_path, "w") as f:
            json.dump({
                "symbol": symbol,
                "pip_size": info.pip_size,
                "pip_value_per_lot": info.pip_value_per_lot,
                "bars_fetched": len(df),
            }, f, indent=2)

        print(f"  Saved {len(df)} bars -> {csv_path}")
        if len(df) < BAR_COUNT:
            print(f"  NOTE: got {len(df)} of {BAR_COUNT} requested bars — "
                  f"likely your broker's history limit, not an error.")

print("\nDone. Copy the data_export/ folder back to compare against the leaderboard.")
