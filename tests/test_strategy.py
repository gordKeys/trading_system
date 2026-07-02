"""
Tests for the strategy layer, using synthetic OHLC data (no MT5 needed
at all — strategy logic should never depend on a live connection).

Run with: python -m tests.test_strategy
"""

import sys
sys.path.insert(0, ".")

import numpy as np
import pandas as pd

from strategy.base import SignalType
from strategy.sma_crossover_example import SMACrossoverStrategy


def make_ohlc(closes: list[float]) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=len(closes), freq="15min")
    return pd.DataFrame({
        "open": closes, "high": closes, "low": closes, "close": closes,
    }, index=idx)


def test_flat_when_insufficient_history():
    strat = SMACrossoverStrategy(fast_period=3, slow_period=5)
    df = make_ohlc([1.10] * 4)  # fewer than slow_period + 1
    signal = strat.generate_signal(df)
    assert signal.signal_type == SignalType.FLAT
    print("PASS: flat signal when not enough history")


def test_bullish_crossover_detected():
    strat = SMACrossoverStrategy(fast_period=2, slow_period=4, stop_pips=20, pip_size=0.0001)
    # Flat, then a sharp bar that flips fast MA above slow MA exactly
    # on the last bar (crossover must be detected on THIS bar, not
    # merely "fast is currently above slow").
    closes = [1.1000, 1.1000, 1.1000, 1.1000, 1.1100]
    df = make_ohlc(closes)
    signal = strat.generate_signal(df)
    assert signal.signal_type == SignalType.BUY, f"Expected BUY, got {signal.signal_type}"
    assert signal.entry_price == 1.1100
    assert abs(signal.stop_loss_price - (1.1100 - 20 * 0.0001)) < 1e-9
    print("PASS: bullish crossover produces BUY signal with correct stop")


def test_bearish_crossover_detected():
    strat = SMACrossoverStrategy(fast_period=2, slow_period=4, stop_pips=20, pip_size=0.0001)
    closes = [1.1100, 1.1100, 1.1100, 1.1100, 1.1000]
    df = make_ohlc(closes)
    signal = strat.generate_signal(df)
    assert signal.signal_type == SignalType.SELL, f"Expected SELL, got {signal.signal_type}"
    assert abs(signal.stop_loss_price - (1.1000 + 20 * 0.0001)) < 1e-9
    print("PASS: bearish crossover produces SELL signal with correct stop")


def test_flat_when_no_crossover():
    strat = SMACrossoverStrategy(fast_period=2, slow_period=4)
    closes = [1.1000, 1.1001, 1.1000, 1.1001, 1.1000, 1.1001]  # flat/choppy, no clean cross
    df = make_ohlc(closes)
    signal = strat.generate_signal(df)
    assert signal.signal_type == SignalType.FLAT
    print("PASS: no false signal on choppy/flat price action")


def test_invalid_period_config_raises():
    try:
        SMACrossoverStrategy(fast_period=10, slow_period=5)
        assert False, "Expected ValueError for fast >= slow"
    except ValueError:
        print("PASS: invalid fast/slow period config raises ValueError")


if __name__ == "__main__":
    test_flat_when_insufficient_history()
    test_bullish_crossover_detected()
    test_bearish_crossover_detected()
    test_flat_when_no_crossover()
    test_invalid_period_config_raises()
    print("\nAll strategy layer tests passed.")
