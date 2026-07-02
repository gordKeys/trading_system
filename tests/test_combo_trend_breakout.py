"""
Tests for TrendConfirmedBreakout.
Run with: python -m tests.test_combo_trend_breakout
"""

import sys
sys.path.insert(0, ".")

import pandas as pd

from strategy.base import SignalType
from strategy.combo_trend_breakout import TrendConfirmedBreakout


def make_ohlc(start: str, bars: list[dict]) -> pd.DataFrame:
    idx = pd.date_range(start, periods=len(bars), freq="15min")
    return pd.DataFrame(bars, index=idx)


def _flat_bar(price: float) -> dict:
    return {"open": price, "high": price + 0.0002, "low": price - 0.0002, "close": price}


def test_breakout_confirmed_by_uptrend_fires():
    strat = TrendConfirmedBreakout(
        session_start_hour=11, range_minutes=30, bar_minutes=15,
        trend_fast_period=2, trend_slow_period=4, stop_buffer_pips=5,
    )
    # Rising baseline so the fast/slow trend MAs agree with an upside breakout.
    bars = [_flat_bar(p) for p in [1.0950, 1.0960, 1.0970, 1.0980]]  # pre-session uptrend
    bars.append({"open": 1.1000, "high": 1.1010, "low": 1.0995, "close": 1.1005})  # 11:00 range bar
    bars.append({"open": 1.1005, "high": 1.1008, "low": 1.0995, "close": 1.1000})  # 11:15 range bar
    bars.append({"open": 1.1005, "high": 1.1030, "low": 1.1005, "close": 1.1025})  # 11:30 breakout up
    df = make_ohlc("2026-01-01 10:00", bars)

    signal = strat.generate_signal(df)
    assert signal.signal_type == SignalType.BUY, f"Expected BUY, got {signal.signal_type}: {signal.reason}"
    print(f"PASS: upside breakout confirmed by uptrend fires BUY ({signal.reason})")


def test_breakout_against_trend_is_skipped():
    strat = TrendConfirmedBreakout(
        session_start_hour=11, range_minutes=30, bar_minutes=15,
        trend_fast_period=2, trend_slow_period=4, stop_buffer_pips=5,
    )
    # Falling baseline (downtrend), but the range breaks to the UPSIDE —
    # should be skipped since trend disagrees with the breakout direction.
    bars = [_flat_bar(p) for p in [1.1050, 1.1040, 1.1030, 1.1020]]  # pre-session downtrend
    bars.append({"open": 1.1000, "high": 1.1010, "low": 1.0995, "close": 1.1005})  # 11:00
    bars.append({"open": 1.1005, "high": 1.1008, "low": 1.0995, "close": 1.1000})  # 11:15
    bars.append({"open": 1.1005, "high": 1.1030, "low": 1.1005, "close": 1.1025})  # breaks UP, but trend is DOWN
    df = make_ohlc("2026-01-01 10:00", bars)

    signal = strat.generate_signal(df)
    assert signal.signal_type == SignalType.FLAT, f"Expected FLAT (trend disagrees), got {signal.signal_type}"
    print("PASS: breakout against the prevailing trend is correctly skipped")


def test_no_breakout_means_no_signal_regardless_of_trend():
    strat = TrendConfirmedBreakout(
        session_start_hour=11, range_minutes=30, bar_minutes=15,
        trend_fast_period=2, trend_slow_period=4, stop_buffer_pips=5,
    )
    bars = [_flat_bar(p) for p in [1.0950, 1.0960, 1.0970, 1.0980]]
    bars.append({"open": 1.1000, "high": 1.1010, "low": 1.0995, "close": 1.1005})
    bars.append({"open": 1.1005, "high": 1.1008, "low": 1.0995, "close": 1.1000})
    bars.append({"open": 1.1005, "high": 1.1009, "low": 1.0996, "close": 1.1002})  # stays inside range
    df = make_ohlc("2026-01-01 10:00", bars)

    signal = strat.generate_signal(df)
    assert signal.signal_type == SignalType.FLAT
    print("PASS: no signal when price stays inside the opening range")


if __name__ == "__main__":
    test_breakout_confirmed_by_uptrend_fires()
    test_breakout_against_trend_is_skipped()
    test_no_breakout_means_no_signal_regardless_of_trend()
    print("\nAll combo trend-confirmed breakout tests passed.")
