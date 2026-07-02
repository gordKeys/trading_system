"""
Strategy leaderboard.

Runs every registered strategy against the SAME historical OHLC data,
using the SAME RiskManager, and prints a ranked comparison table.

Usage:
    python -m validation.leaderboard --csv path/to/EURUSD_M15.csv

The CSV must have columns: time, open, high, low, close
(export this from MT5 on your VPS — see data/market_data.py for the
schema fetch_ohlc/fetch_ohlc_range produce; save with df.to_csv()).

Without --csv, this runs against small synthetic demo data instead —
useful for confirming the pipeline works, USELESS for actually
choosing a strategy. Real strategy selection requires real history.
"""

import argparse
import sys

import numpy as np
import pandas as pd

from risk.risk_manager import RiskManager
from execution.backtest_executor import run_backtest
from validation.metrics import compute_metrics, PerformanceMetrics

from strategy.sma_crossover_example import SMACrossoverStrategy
from strategy.orb_breakout import OpeningRangeBreakout
from strategy.trend_following_ma import TrendFollowingMA
from strategy.mean_reversion_rsi import MeanReversionRSI
from strategy.combo_trend_breakout import TrendConfirmedBreakout


def build_strategies() -> list:
    """
    Fresh instance per strategy per run — some (ORB, combo) carry
    day-state and must never be reused across runs (see their docstrings).
    """
    return [
        SMACrossoverStrategy(fast_period=10, slow_period=30, stop_pips=20),
        OpeningRangeBreakout(session_start_hour=11, range_minutes=30, bar_minutes=15),
        TrendFollowingMA(fast_period=10, slow_period=30, slope_lookback=5, stop_pips=25),
        MeanReversionRSI(rsi_period=14, oversold=30, overbought=70, stop_pips=20),
        TrendConfirmedBreakout(session_start_hour=11, range_minutes=30, bar_minutes=15,
                                trend_fast_period=10, trend_slow_period=30),
    ]


def load_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["time"])
    df = df.set_index("time").sort_index()
    required = {"open", "high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"CSV missing required columns: {missing}")
    return df


def generate_synthetic_demo_data(bars: int = 2000, seed: int = 7) -> pd.DataFrame:
    """
    Random-walk placeholder data — ONLY for confirming the leaderboard
    pipeline runs end-to-end without crashing. Every strategy will look
    roughly like noise-trading on this, which is expected: random walks
    have no real breakouts, no real trends, no real mean-reversion.
    Do not use these numbers to pick a strategy.
    """
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-01-01 00:00", periods=bars, freq="15min")
    returns = rng.normal(0, 0.0003, size=bars)
    close = 1.1000 + np.cumsum(returns)
    high = close + np.abs(rng.normal(0, 0.0002, size=bars))
    low = close - np.abs(rng.normal(0, 0.0002, size=bars))
    open_ = close - returns
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close}, index=idx)


def run_leaderboard(
    ohlc: pd.DataFrame,
    initial_balance: float = 10_000.0,
    pip_value_per_lot: float = 10.0,
    pip_size: float = 0.0001,
) -> list[PerformanceMetrics]:
    rm = RiskManager()
    results = []
    for strategy in build_strategies():
        backtest_result = run_backtest(
            strategy=strategy,
            ohlc=ohlc,
            initial_balance=initial_balance,
            pip_value_per_lot=pip_value_per_lot,
            pip_size=pip_size,
            risk_manager=rm,
            warmup_bars=50,
        )
        metrics = compute_metrics(backtest_result, initial_balance=initial_balance)
        results.append(metrics)

    results.sort(key=lambda m: m.total_return_pct, reverse=True)
    return results


def print_leaderboard(results: list[PerformanceMetrics]) -> None:
    header = f"{'strategy':<32}{'trades':>8}{'win%':>8}{'return%':>10}{'maxDD%':>9}{'PF':>8}{'blocked':>9}"
    print(header)
    print("-" * len(header))
    for m in results:
        pf_str = f"{m.profit_factor:.2f}" if m.profit_factor is not None else "n/a"
        print(f"{m.strategy_name:<32}{m.total_trades:>8}{m.win_rate_pct:>7.1f}%{m.total_return_pct:>9.2f}%"
              f"{m.max_drawdown_pct:>8.2f}%{pf_str:>8}{m.blocked_signal_count:>9}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the strategy leaderboard.")
    parser.add_argument("--csv", type=str, default=None, help="Path to a historical OHLC CSV (time,open,high,low,close)")
    parser.add_argument("--balance", type=float, default=10_000.0)
    parser.add_argument("--pip-value", type=float, default=10.0)
    args = parser.parse_args()

    if args.csv:
        data = load_csv(args.csv)
        print(f"Loaded {len(data)} bars from {args.csv}\n")
    else:
        print("WARNING: no --csv given — using synthetic random-walk demo data.")
        print("This only proves the pipeline runs; it tells you NOTHING about which")
        print("strategy is actually good. Export real MT5 history and re-run with --csv.\n")
        data = generate_synthetic_demo_data()

    leaderboard = run_leaderboard(data, initial_balance=args.balance, pip_value_per_lot=args.pip_value)
    print_leaderboard(leaderboard)
