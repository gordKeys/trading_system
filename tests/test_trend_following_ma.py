"""
Tests for TrendFollowingMA.
Run with: python -m tests.test_trend_following_ma
"""

import sys
sys.path.insert(0, ".")

import pandas as pd

from strategy.base import SignalType
from strategy.trend_following_ma import TrendFollowingMA


def make_ohlc(closes: list[float]) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=len(closes), freq="15min")
    return pd.DataFrame({"open": closes, "high": closes, "low": closes, "close": closes}, index=idx)


def test_flat_when_insufficient_history():
    strat = TrendFollowingMA(fast_period=3, slow_period=5, slope_lookback=2)
    df = make_ohlc([1.10] * 5)
    signal = strat.generate_signal(df)
    assert signal.signal_type == SignalType.FLAT
    print("PASS: flat when not enough history for slope lookback")


def test_crossover_with_confirming_slope_produces_buy():
    strat = TrendFollowingMA(fast_period=2, slow_period=4, slope_lookback=1, stop_pips=25, pip_size=0.0001)
    # Flat, then a sharp bar that flips fast MA above slow MA exactly
    # on the last bar, with the slow MA slope already turning positive.
    closes = [1.1000, 1.1000, 1.1000, 1.1000, 1.1000, 1.1100]
    df = make_ohlc(closes)
    signal = strat.generate_signal(df)
    assert signal.signal_type == SignalType.BUY, f"Expected BUY, got {signal.signal_type}"
    print("PASS: crossover confirmed by rising slope produces BUY")


def test_crossover_against_slope_is_filtered_out():
    # Deliberately constructed: a net decline followed by one sharp bar
    # big enough to flip the raw fast/slow crossover, while the slow
    # MA's slope (measured over the lookback) is STILL negative. The
    # trend filter must block this, even though a naive crossover
    # strategy would fire a BUY here.
    strat = TrendFollowingMA(fast_period=2, slow_period=4, slope_lookback=1, stop_pips=25, pip_size=0.0001)
    closes = [1.1000, 1.0990, 1.0965, 1.0940, 1.0965, 1.0975]
    df = make_ohlc(closes)

    # Sanity-check the raw crossover WOULD have fired, to prove the
    # filter is actually doing something (not just a coincidental FLAT).
    fast_ma = df["close"].rolling(2).mean()
    slow_ma = df["close"].rolling(4).mean()
    crossed_up = fast_ma.iloc[-2] <= slow_ma.iloc[-2] and fast_ma.iloc[-1] > slow_ma.iloc[-1]
    slow_slope = slow_ma.iloc[-1] - slow_ma.iloc[-2]
    assert crossed_up, "Test setup error: expected a raw crossover on this synthetic data"
    assert slow_slope < 0, "Test setup error: expected the slow MA slope to still be negative"

    signal = strat.generate_signal(df)
    assert signal.signal_type == SignalType.FLAT, (
        f"Expected the trend filter to block a crossover against the slope, got {signal.signal_type}"
    )
    print("PASS: crossover against the broader slope is filtered out")


def test_invalid_periods_raise():
    try:
        TrendFollowingMA(fast_period=10, slow_period=5)
        assert False
    except ValueError:
        print("PASS: invalid fast/slow period raises ValueError")


if __name__ == "__main__":
    test_flat_when_insufficient_history()
    test_crossover_with_confirming_slope_produces_buy()
    test_crossover_against_slope_is_filtered_out()
    test_invalid_periods_raise()
    print("\nAll trend-following MA tests passed.")
