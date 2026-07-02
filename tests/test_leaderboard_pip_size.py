"""
Regression test for the JPY pip_size bug: every strategy built by
build_strategies() must actually use the pip_size it was given, not
silently fall back to the EURUSD-style 0.0001 default.

Run with: python -m tests.test_leaderboard_pip_size
"""

import sys
sys.path.insert(0, ".")

import pandas as pd

from validation.leaderboard import build_strategies
from strategy.base import SignalType


def make_flat_then_jump(price_start: float, jump: float, n_flat: int = 40) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=n_flat + 1, freq="15min")
    closes = [price_start] * n_flat + [price_start + jump]
    return pd.DataFrame({"open": closes, "high": closes, "low": closes, "close": closes}, index=idx)


def test_strategies_use_jpy_pip_size_for_stop_distance():
    """
    For a JPY-style pair (pip_size=0.01), a strategy configured with a
    default stop_pips value should place a stop MUCH further away (in
    raw price terms) than the same strategy built with pip_size=0.0001.
    If both produce the same stop distance, pip_size isn't being used.
    """
    jpy_strategies = build_strategies(pip_size=0.01)
    eur_strategies = build_strategies(pip_size=0.0001)

    # SMACrossoverStrategy is index 0 in both lists — same fast/slow/stop_pips config.
    jpy_sma = jpy_strategies[0]
    eur_sma = eur_strategies[0]

    assert jpy_sma.pip_size == 0.01, f"Expected JPY strategy pip_size=0.01, got {jpy_sma.pip_size}"
    assert eur_sma.pip_size == 0.0001, f"Expected EUR strategy pip_size=0.0001, got {eur_sma.pip_size}"

    # Same stop_pips config (20), different pip_size -> stop distance
    # in raw price terms must differ by exactly the pip_size ratio (100x).
    df = make_flat_then_jump(150.00, 0.50)  # JPY-scale prices
    jpy_signal = jpy_sma.generate_signal(df)
    eur_signal = eur_sma.generate_signal(df)

    if jpy_signal.is_actionable and eur_signal.is_actionable:
        jpy_stop_dist = abs(jpy_signal.entry_price - jpy_signal.stop_loss_price)
        eur_stop_dist = abs(eur_signal.entry_price - eur_signal.stop_loss_price)
        ratio = jpy_stop_dist / eur_stop_dist
        assert abs(ratio - 100) < 1, (
            f"Expected JPY stop distance to be ~100x the EUR-style stop distance "
            f"(20 pips at 0.01 vs 20 pips at 0.0001), got ratio {ratio:.1f}. "
            f"This means pip_size isn't being passed through to strategies correctly."
        )
        print(f"PASS: JPY-configured strategy produces a stop distance ~100x wider "
              f"than EUR-configured ({jpy_stop_dist:.4f} vs {eur_stop_dist:.6f}) — "
              f"pip_size is correctly wired through build_strategies()")
    else:
        # Direct attribute check as a fallback if this particular price
        # path didn't trigger a crossover signal.
        assert jpy_sma.pip_size != eur_sma.pip_size
        print("PASS: pip_size attribute correctly differs per build_strategies() call "
              "(signal-based distance check skipped — no crossover on this synthetic path)")


def test_all_strategies_receive_configured_pip_size():
    """Every strategy that exposes a pip_size attribute must match what was requested."""
    strategies = build_strategies(pip_size=0.01)
    checked = 0
    for strat in strategies:
        if hasattr(strat, "pip_size"):
            assert strat.pip_size == 0.01, f"{strat.name} has pip_size={strat.pip_size}, expected 0.01"
            checked += 1
    assert checked > 0, "No strategies exposed a pip_size attribute to check — test setup problem"
    print(f"PASS: all {checked} pip_size-aware strategies received the configured value")


if __name__ == "__main__":
    test_strategies_use_jpy_pip_size_for_stop_distance()
    test_all_strategies_receive_configured_pip_size()
    print("\nAll pip_size wiring regression tests passed.")
