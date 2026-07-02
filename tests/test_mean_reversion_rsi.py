"""
Tests for MeanReversionRSI.
Run with: python -m tests.test_mean_reversion_rsi
"""

import sys
sys.path.insert(0, ".")

import pandas as pd

from strategy.base import SignalType
from strategy.mean_reversion_rsi import MeanReversionRSI, _rsi


def make_ohlc(closes: list[float]) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=len(closes), freq="15min")
    return pd.DataFrame({"open": closes, "high": closes, "low": closes, "close": closes}, index=idx)


def test_rsi_all_gains_approaches_100():
    closes = pd.Series([1.10 + i * 0.001 for i in range(20)])
    rsi = _rsi(closes, period=14)
    assert rsi.iloc[-1] > 90, f"Expected RSI near 100 for all-gains series, got {rsi.iloc[-1]}"
    print("PASS: RSI approaches 100 for a strictly increasing series")


def test_rsi_all_losses_approaches_0():
    closes = pd.Series([1.20 - i * 0.001 for i in range(20)])
    rsi = _rsi(closes, period=14)
    assert rsi.iloc[-1] < 10, f"Expected RSI near 0 for all-losses series, got {rsi.iloc[-1]}"
    print("PASS: RSI approaches 0 for a strictly decreasing series")


def test_flat_when_insufficient_history():
    strat = MeanReversionRSI(rsi_period=14)
    df = make_ohlc([1.10] * 10)
    signal = strat.generate_signal(df)
    assert signal.signal_type == SignalType.FLAT
    print("PASS: flat when not enough history for RSI period")


def test_reversal_out_of_oversold_produces_buy():
    strat = MeanReversionRSI(rsi_period=5, oversold=30, overbought=70, stop_pips=20, pip_size=0.0001)
    # Sharp decline (pushes RSI well below 30), then a bounce bar to
    # trigger the "crossing back above oversold" signal.
    closes = [1.1100, 1.1080, 1.1060, 1.1040, 1.1020, 1.1000, 1.0990, 1.1020]
    df = make_ohlc(closes)
    signal = strat.generate_signal(df)
    assert signal.signal_type == SignalType.BUY, f"Expected BUY, got {signal.signal_type}: {signal.reason}"
    print(f"PASS: reversal out of oversold produces BUY ({signal.reason})")


def test_reversal_out_of_overbought_produces_sell():
    strat = MeanReversionRSI(rsi_period=5, oversold=30, overbought=70, stop_pips=20, pip_size=0.0001)
    closes = [1.1000, 1.1020, 1.1040, 1.1060, 1.1080, 1.1100, 1.1110, 1.1060]
    df = make_ohlc(closes)
    signal = strat.generate_signal(df)
    assert signal.signal_type == SignalType.SELL, f"Expected SELL, got {signal.signal_type}: {signal.reason}"
    print(f"PASS: reversal out of overbought produces SELL ({signal.reason})")


def test_flat_when_no_extreme_reached():
    strat = MeanReversionRSI(rsi_period=5, oversold=30, overbought=70)
    closes = [1.1000, 1.1002, 1.0999, 1.1001, 1.1000, 1.1003, 1.0998, 1.1000]
    df = make_ohlc(closes)
    signal = strat.generate_signal(df)
    assert signal.signal_type == SignalType.FLAT
    print("PASS: no signal when RSI stays in the neutral zone")


if __name__ == "__main__":
    test_rsi_all_gains_approaches_100()
    test_rsi_all_losses_approaches_0()
    test_flat_when_insufficient_history()
    test_reversal_out_of_oversold_produces_buy()
    test_reversal_out_of_overbought_produces_sell()
    test_flat_when_no_extreme_reached()
    print("\nAll mean-reversion RSI tests passed.")
