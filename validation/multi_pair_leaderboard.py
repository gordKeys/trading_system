"""
Multi-pair leaderboard.

Runs every strategy against every pair's exported data and prints:
  1. A full metrics table per pair (same as validation.leaderboard)
  2. A summary matrix: strategy x pair -> total return %
  3. A "best combos" callout: which strategy performed best on which pair

Usage:
    python -m validation.multi_pair_leaderboard --dir data_export

Expects a directory produced by export_data.py: <SYMBOL>_M15.csv +
<SYMBOL>_meta.json pairs for each symbol.
"""

import argparse
import glob
import json
import os

import pandas as pd

from validation.leaderboard import run_leaderboard, print_leaderboard, load_csv
from validation.metrics import PerformanceMetrics


def discover_pairs(directory: str) -> list[tuple[str, str, str]]:
    """Returns list of (symbol, csv_path, meta_path) found in directory."""
    pairs = []
    for csv_path in sorted(glob.glob(os.path.join(directory, "*_M15.csv"))):
        symbol = os.path.basename(csv_path).replace("_M15.csv", "")
        meta_path = os.path.join(directory, f"{symbol}_meta.json")
        if not os.path.exists(meta_path):
            print(f"WARNING: no metadata file for {symbol}, skipping (need {meta_path})")
            continue
        pairs.append((symbol, csv_path, meta_path))
    return pairs


def run_multi_pair(directory: str, initial_balance: float = 10_000.0) -> dict[str, list[PerformanceMetrics]]:
    pairs = discover_pairs(directory)
    if not pairs:
        raise FileNotFoundError(f"No <SYMBOL>_M15.csv + _meta.json pairs found in {directory}")

    all_results = {}
    for symbol, csv_path, meta_path in pairs:
        with open(meta_path) as f:
            meta = json.load(f)

        data = load_csv(csv_path)
        print(f"\n=== {symbol} ({len(data)} bars, pip_size={meta['pip_size']}, "
              f"pip_value_per_lot={meta['pip_value_per_lot']:.2f}) ===")

        results = run_leaderboard(
            data,
            initial_balance=initial_balance,
            pip_value_per_lot=meta["pip_value_per_lot"],
            pip_size=meta["pip_size"],
        )
        print_leaderboard(results)
        all_results[symbol] = results

    return all_results


def print_summary_matrix(all_results: dict[str, list[PerformanceMetrics]]) -> None:
    strategy_names = sorted({m.strategy_name for results in all_results.values() for m in results})
    symbols = list(all_results.keys())

    print("\n\n=== SUMMARY: total return % by strategy x pair ===")
    header = f"{'strategy':<32}" + "".join(f"{s:>12}" for s in symbols)
    print(header)
    print("-" * len(header))

    for strat_name in strategy_names:
        row = f"{strat_name:<32}"
        for symbol in symbols:
            metrics = next((m for m in all_results[symbol] if m.strategy_name == strat_name), None)
            row += f"{metrics.total_return_pct:>11.2f}%" if metrics else f"{'n/a':>12}"
        print(row)

    print("\n=== BEST STRATEGY PER PAIR (by total return) ===")
    for symbol, results in all_results.items():
        best = max(results, key=lambda m: m.total_return_pct)
        pf_str = f"{best.profit_factor:.2f}" if best.profit_factor is not None else "n/a"
        print(f"  {symbol:<10} -> {best.strategy_name:<32} "
              f"({best.total_return_pct:+.2f}%, {best.total_trades} trades, PF={pf_str})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the leaderboard across multiple pairs.")
    parser.add_argument("--dir", type=str, default="data_export", help="Directory with exported CSV+meta pairs")
    parser.add_argument("--balance", type=float, default=10_000.0)
    args = parser.parse_args()

    all_results = run_multi_pair(args.dir, initial_balance=args.balance)
    print_summary_matrix(all_results)
