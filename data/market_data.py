"""
Historical and live market data fetching.

Returns pandas DataFrames so strategy/backtest code has one consistent
data shape regardless of source. Column names are fixed on purpose
(open/high/low/close/tick_volume/spread/time) so strategy code never
needs to know it's talking to MT5 specifically — this is what lets the
backtest engine later replay the exact same DataFrame shape from a
cached CSV instead of a live connection.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

import pandas as pd

from data.mt5_connector import MT5Connector, MT5ConnectionError


class Timeframe(Enum):
    """
    Maps our own timeframe names to MT5's TIMEFRAME_* constants.
    Kept as an enum of strings (not the raw mt5 int constants) so this
    module can be imported and the enum used in tests/config without
    ever touching the real MT5 package.
    """
    M1 = "M1"
    M5 = "M5"
    M15 = "M15"
    M30 = "M30"
    H1 = "H1"
    H4 = "H4"
    D1 = "D1"


def _resolve_mt5_timeframe(mt5, timeframe: Timeframe):
    mapping = {
        Timeframe.M1: mt5.TIMEFRAME_M1,
        Timeframe.M5: mt5.TIMEFRAME_M5,
        Timeframe.M15: mt5.TIMEFRAME_M15,
        Timeframe.M30: mt5.TIMEFRAME_M30,
        Timeframe.H1: mt5.TIMEFRAME_H1,
        Timeframe.H4: mt5.TIMEFRAME_H4,
        Timeframe.D1: mt5.TIMEFRAME_D1,
    }
    return mapping[timeframe]


def fetch_ohlc(
    connector: MT5Connector,
    symbol: str,
    timeframe: Timeframe,
    count: int,
) -> pd.DataFrame:
    """
    Fetch the most recent `count` bars for `symbol` at `timeframe`.

    Returns a DataFrame indexed by UTC datetime, columns:
    open, high, low, close, tick_volume, spread, real_volume

    Note: MT5 returns bars in server time, not UTC. This does NOT
    convert timezones — that requires knowing your broker's server UTC
    offset (varies by broker and DST). Confirm this before relying on
    bar timestamps for anything session-boundary-sensitive (e.g. the
    London session logic in an ORB-style strategy).
    """
    mt5 = connector.mt5
    mt5_timeframe = _resolve_mt5_timeframe(mt5, timeframe)

    rates = mt5.copy_rates_from_pos(symbol, mt5_timeframe, 0, count)
    if rates is None or len(rates) == 0:
        error = mt5.last_error()
        raise MT5ConnectionError(
            f"copy_rates_from_pos returned no data for {symbol} {timeframe.value}: {error}"
        )

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df = df.set_index("time")
    return df[["open", "high", "low", "close", "tick_volume", "spread", "real_volume"]]


def fetch_ohlc_range(
    connector: MT5Connector,
    symbol: str,
    timeframe: Timeframe,
    date_from: datetime,
    date_to: datetime,
) -> pd.DataFrame:
    """
    Fetch bars for `symbol` at `timeframe` between two datetimes
    (server time — see fetch_ohlc's timezone note). Used for building
    backtest datasets over a specific historical window.
    """
    mt5 = connector.mt5
    mt5_timeframe = _resolve_mt5_timeframe(mt5, timeframe)

    rates = mt5.copy_rates_range(symbol, mt5_timeframe, date_from, date_to)
    if rates is None or len(rates) == 0:
        error = mt5.last_error()
        raise MT5ConnectionError(
            f"copy_rates_range returned no data for {symbol} {timeframe.value} "
            f"between {date_from} and {date_to}: {error}"
        )

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df = df.set_index("time")
    return df[["open", "high", "low", "close", "tick_volume", "spread", "real_volume"]]


@dataclass(frozen=True)
class Tick:
    time: datetime
    bid: float
    ask: float
    last: float


def fetch_latest_tick(connector: MT5Connector, symbol: str) -> Tick:
    """
    Fetch the current bid/ask for `symbol` — used by the live bot loop.

    Timestamp decoding must match fetch_ohlc/fetch_ohlc_range exactly:
    we decode the raw epoch with no local-timezone conversion, so tick
    time and bar time are always comparable. Using datetime.fromtimestamp()
    here (instead of utcfromtimestamp) previously applied the *system's*
    local timezone on top of the epoch, silently shifting tick time
    away from bar time by whatever offset the machine running this is
    set to — a bug that showed up as tick time reading ~2 hours ahead
    of the latest bar on a VPS set to UTC+2.
    """
    mt5 = connector.mt5
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        error = mt5.last_error()
        raise MT5ConnectionError(f"symbol_info_tick returned None for {symbol}: {error}")

    return Tick(
        time=datetime.utcfromtimestamp(tick.time),
        bid=tick.bid,
        ask=tick.ask,
        last=tick.last,
    )
