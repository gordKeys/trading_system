"""
One-off diagnostic: measures the offset between MT5's server clock
(as reported in tick timestamps) and true UTC.

Run this on the VPS with the MT5 terminal open and logged in:
    python check_server_offset.py

Read the printed offset and put it in config/settings.py or wherever
we end up needing it for session-boundary logic (e.g. London open).
"""

from datetime import datetime, timezone

from data.mt5_connector import MT5Connector
from data.market_data import fetch_latest_tick

SYMBOL = "EURUSD"

with MT5Connector() as conn:
    real_utc_now = datetime.now(timezone.utc).replace(tzinfo=None)
    tick = fetch_latest_tick(conn, SYMBOL)

    diff = tick.time - real_utc_now
    hours = diff.total_seconds() / 3600

    print(f"Real UTC now:        {real_utc_now}")
    print(f"MT5 server tick time: {tick.time}")
    print(f"Difference:           {hours:+.2f} hours")
    print()
    print(f"Broker server clock appears to run UTC{hours:+.0f} "
          f"(re-run at a different time of day/year to check for DST drift).")
