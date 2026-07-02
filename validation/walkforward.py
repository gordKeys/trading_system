"""
Segmented (walkforward-style) validation.

Splits historical OHLC data into N sequential, non-overlapping time
segments and runs a strategy independently on each one — a fresh
strategy instance and a fresh $10k account per segment, so no state or
capital carries over between segments. This answers a different
question than the single-window leaderboard: not "is this profitable
over the whole dataset" but "is it CONSISTENTLY profitable across
different sub-periods, or did the aggregate result come from one lucky
stretch."

IMPORTANT — what this is NOT: this does not re-optimize parameters per
segment (we have no parameter optimizer yet). This is segmented
out-of-sample consistency testing with FIXED parameters throughout,
not full walkforward-with-reoptimization. That's a reasonable next
step in its own right, but don't call this "walkforward validation" in
the strict sense without adding a parameter search step.
"""

import argparse

import numpy as np
import pandas as pd

from risk.risk_manager import RiskManager
from execution.backtest_executor import run_backtest
from validation.metrics import compute_metrics, PerformanceMetrics
from validation.leaderboard import load_csv

from strategy.sma_crossover_example import SMACrossoverStrategy
from strategy.orb_breakout import OpeningRangeBreakout
from strategy.trend_following_ma import TrendFollowingMA
from strategy.mean_reversion_rsi import MeanReversionRSI
from strategy.combo_trend_breakout import TrendConfirmedBreakout


STRATEGY_BUILDERS = {
    "sma_crossover_example": lambda pip_size: SMACrossoverStrategy(fast_period=10, slow_period=30, stop_pips=20, pip_size=pip_size),
    "orb_breakout": lambda pip_size: OpeningRangeBreakout(session_start_hour=11, range_minutes=30, bar_minutes=15, pip_size=pip_size),
    "trend_following_ma": lambda pip_size: TrendFollowingMA(fast_period=10, slow_period=30, slope_lookback=5, stop_pips=25, pip_size=pip_size),
    "mean_reversion_rsi": lambda pip_size: MeanReversionRSI(rsi_period=14, oversold=30, overbought=70, stop_pips=20, pip_size=pip_size),
    "combo_trend_confirmed_breakout": lambda pip_size: TrendConfirmedBreakout(
        session_start_hour=11, range_minutes=30, bar_minutes=15,
        trend_fast_period=10, trend_slow_period=30, pip_size=pip_size),
}


def split_into_segments(ohlc: pd.DataFrame, n_segments: int) -> list[pd.DataFrame]:
    """
    Split chronologically into n_segments contiguous, non-overlapping
    chunks. Each chunk still gets `warmup_bars` worth of lookback
    "wasted" at its start (the strategy has no history before the
    segment boundary) — this is a real limitation: segments will show
    slightly fewer effective trading bars than a continuous run would,
    especially for short segments. Prefer more bars per segment over
    more segments when the two trade off.
    """
    if n_segments < 2:
        raise ValueError("n_segments must be at least 2 to test consistency")
    boundaries = np.linspace(0, len(ohlc), n_segments + 1, dtype=int)
    return [ohlc.iloc[boundaries[i]:boundaries[i + 1]] for i in range(n_segments)]


def run_segmented_analysis(
    strategy_name: str,
    ohlc: pd.DataFrame,
    n_segments: int = 5,
    initial_balance: float = 10_000.0,
    pip_value_per_lot: float = 10.0,
    pip_size: float = 0.0001,
    warmup_bars: int = 50,
) -> list[PerformanceMetrics]:
    if strategy_name not in STRATEGY_BUILDERS:
        raise ValueError(f"Unknown strategy '{strategy_name}'. Options: {list(STRATEGY_BUILDERS)}")

    segments = split_into_segments(ohlc, n_segments)
    results = []
    for i, segment in enumerate(segments):
        strategy = STRATEGY_BUILDERS[strategy_name](pip_size)  # fresh instance per segment
        rm = RiskManager()  # fresh risk state per segment
        backtest_result = run_backtest(
            strategy=strategy,
            ohlc=segment,
            initial_balance=initial_balance,
            pip_value_per_lot=pip_value_per_lot,
            pip_size=pip_size,
            risk_manager=rm,
            warmup_bars=warmup_bars,
        )
        metrics = compute_metrics(backtest_result, initial_balance=initial_balance)
        metrics.strategy_name = f"segment_{i+1} ({segment.index[0].date()} to {segment.index[-1].date()})"
        results.append(metrics)
    return results


def print_segment_results(results: list[PerformanceMetrics]) -> None:
    header = f"{'segment':<38}{'trades':>8}{'win%':>8}{'return%':>10}{'maxDD%':>9}{'PF':>8}{'blocked':>9}"
    print(header)
    print("-" * len(header))
    for m in results:
        pf_str = f"{m.profit_factor:.2f}" if m.profit_factor is not None else "n/a"
        print(f"{m.strategy_name:<38}{m.total_trades:>8}{m.win_rate_pct:>7.1f}%{m.total_return_pct:>9.2f}%"
              f"{m.max_drawdown_pct:>8.2f}%{pf_str:>8}{m.blocked_signal_count:>9}")

    returns = [m.total_return_pct for m in results]
    profitable_segments = sum(1 for r in returns if r > 0)
    blown_segments = sum(1 for m in results if m.blocked_signal_count > 0)

    print()
    print(f"Profitable segments: {profitable_segments}/{len(results)}")
    print(f"Segments that blew the drawdown safety buffer: {blown_segments}/{len(results)}")
    print(f"Return range: {min(returns):+.2f}% to {max(returns):+.2f}% "
          f"(mean {np.mean(returns):+.2f}%, std {np.std(returns):.2f}%)")

    if blown_segments > 0:
        print("\nWARNING: at least one segment blew the drawdown safety buffer — "
              "this strategy would have failed the FTMO challenge in that period, "
              "regardless of how the aggregate/other segments look.")
    if profitable_segments < len(results) * 0.6:
        print("\nCAUTION: profitable in fewer than 60% of segments — the aggregate "
              "result on the full dataset is likely being carried by one or two "
              "strong segments rather than reflecting consistent behavior.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Segmented (walkforward-style) consistency testing for one strategy.")
    parser.add_argument("--csv", type=str, required=True)
    parser.add_argument("--strategy", type=str, required=True, choices=list(STRATEGY_BUILDERS))
    parser.add_argument("--segments", type=int, default=5)
    parser.add_argument("--balance", type=float, default=10_000.0)
    parser.add_argument("--pip-value", type=float, default=10.0)
    parser.add_argument("--pip-size", type=float, default=0.0001)
    args = parser.parse_args()

    data = load_csv(args.csv)
    print(f"Loaded {len(data)} bars from {args.csv}, splitting into {args.segments} segments\n")

    results = run_segmented_analysis(
        strategy_name=args.strategy,
        ohlc=data,
        n_segments=args.segments,
        initial_balance=args.balance,
        pip_value_per_lot=args.pip_value,
        pip_size=args.pip_size,
    )
    print_segment_results(results)
