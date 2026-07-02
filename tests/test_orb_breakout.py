"""
Tests for OpeningRangeBreakout.
Run with: python -m tests.test_orb_breakout
"""

import sys
sys.path.insert(0, ".")

import pandas as pd

from strategy.base import SignalType
from strategy.orb_breakout import OpeningRangeBreakout


def make_ohlc(start: str, bars: list[dict]) -> pd.DataFrame:
    idx = pd.date_range(start, periods=len(bars), freq="15min")
    return pd.DataFrame(bars, index=idx)


def _flat_bar(price: float) -> dict:
    return {"open": price, "high": price + 0.0002, "low": price - 0.0002, "close": price}


def test_flat_before_session():
    strat = OpeningRangeBreakout(session_start_hour=11, range_minutes=30, bar_minutes=15)
    bars = [_flat_bar(1.1000) for _ in range(4)]  # 10:00 - 10:45, before session hour
    df = make_ohlc("2026-01-01 10:00", bars)
    signal = strat.generate_signal(df)
    assert signal.signal_type == SignalType.FLAT
    print("PASS: no signal before the session's range window forms")


def test_bullish_breakout_above_range():
    strat = OpeningRangeBreakout(session_start_hour=11, range_minutes=30, bar_minutes=15, stop_buffer_pips=5)
    bars = [_flat_bar(1.1000) for _ in range(4)]  # 10:00 - 10:45 padding
    # Range-forming bars at 11:00 and 11:15
    bars.append({"open": 1.1000, "high": 1.1010, "low": 1.0995, "close": 1.1005})  # 11:00
    bars.append({"open": 1.1005, "high": 1.1008, "low": 1.0990, "close": 1.1000})  # 11:15
    # Breakout bar at 11:30, closes above range high 1.1010
    bars.append({"open": 1.1005, "high": 1.1030, "low": 1.1005, "close": 1.1025})  # 11:30
    df = make_ohlc("2026-01-01 10:00", bars)

    signal = strat.generate_signal(df)
    assert signal.signal_type == SignalType.BUY, f"Expected BUY, got {signal.signal_type}: {signal.reason}"
    assert signal.entry_price == 1.1025
    assert signal.stop_loss_price < 1.0990  # below range low minus buffer
    print(f"PASS: bullish breakout above range detected ({signal.reason})")


def test_bearish_breakout_below_range():
    strat = OpeningRangeBreakout(session_start_hour=11, range_minutes=30, bar_minutes=15, stop_buffer_pips=5)
    bars = [_flat_bar(1.1000) for _ in range(4)]
    bars.append({"open": 1.1000, "high": 1.1010, "low": 1.0995, "close": 1.1000})  # 11:00
    bars.append({"open": 1.1000, "high": 1.1005, "low": 1.0990, "close": 1.0995})  # 11:15
    bars.append({"open": 1.0995, "high": 1.0995, "low": 1.0970, "close": 1.0975})  # 11:30, breaks below 1.0990
    df = make_ohlc("2026-01-01 10:00", bars)

    signal = strat.generate_signal(df)
    assert signal.signal_type == SignalType.SELL, f"Expected SELL, got {signal.signal_type}: {signal.reason}"
    assert signal.entry_price == 1.0975
    print(f"PASS: bearish breakout below range detected ({signal.reason})")


def test_only_trades_once_per_session():
    strat = OpeningRangeBreakout(session_start_hour=11, range_minutes=30, bar_minutes=15, stop_buffer_pips=5)
    bars = [_flat_bar(1.1000) for _ in range(4)]
    bars.append({"open": 1.1000, "high": 1.1010, "low": 1.0995, "close": 1.1005})
    bars.append({"open": 1.1005, "high": 1.1008, "low": 1.0990, "close": 1.1000})
    bars.append({"open": 1.1005, "high": 1.1030, "low": 1.1005, "close": 1.1025})  # breakout #1
    bars.append({"open": 1.1025, "high": 1.1050, "low": 1.1020, "close": 1.1040})  # would ALSO look breakout-y
    df = make_ohlc("2026-01-01 10:00", bars)

    first_signal = strat.generate_signal(df.iloc[:-1])
    assert first_signal.is_actionable
    second_signal = strat.generate_signal(df)
    assert second_signal.signal_type == SignalType.FLAT, "Expected no second trade in the same session"
    print("PASS: strategy trades at most once per session")


if __name__ == "__main__":
    test_flat_before_session()
    test_bullish_breakout_above_range()
    test_bearish_breakout_below_range()
    test_only_trades_once_per_session()
    print("\nAll ORB breakout tests passed.")
