"""
Tests for validation/metrics.py.
Run with: python -m tests.test_metrics
"""

import sys
sys.path.insert(0, ".")

from datetime import datetime

from execution.backtest_executor import BacktestResult, Trade, ExitReason
from strategy.base import SignalType
from validation.metrics import compute_metrics


def make_trade(pnl: float) -> Trade:
    return Trade(
        direction=SignalType.BUY,
        entry_time=datetime(2026, 1, 1),
        entry_price=1.1000,
        stop_loss_price=1.0980,
        take_profit_price=1.1040,
        lot_size=0.1,
        exit_time=datetime(2026, 1, 1, 1),
        exit_price=1.1010,
        exit_reason=ExitReason.TAKE_PROFIT if pnl > 0 else ExitReason.STOP_LOSS,
        pnl=pnl,
    )


def test_no_trades_gives_zeroed_metrics():
    result = BacktestResult(strategy_name="test", trades=[], equity_curve=[10_000] * 5)
    metrics = compute_metrics(result, initial_balance=10_000)
    assert metrics.total_trades == 0
    assert metrics.total_return_pct == 0.0
    assert metrics.profit_factor is None
    print("PASS: zero trades gives zeroed metrics, no divide-by-zero")


def test_win_rate_and_return_computed_correctly():
    trades = [make_trade(100), make_trade(100), make_trade(-50)]
    result = BacktestResult(
        strategy_name="test", trades=trades,
        equity_curve=[10_000, 10_100, 10_200, 10_150],
        final_balance=10_150,
    )
    metrics = compute_metrics(result, initial_balance=10_000)
    assert abs(metrics.win_rate_pct - (2 / 3 * 100)) < 0.01
    assert abs(metrics.total_return_pct - 1.5) < 0.01  # (10150-10000)/10000 * 100
    print(f"PASS: win rate {metrics.win_rate_pct:.1f}%, return {metrics.total_return_pct:.2f}% computed correctly")


def test_profit_factor_none_when_no_losses():
    trades = [make_trade(100), make_trade(50)]
    result = BacktestResult(strategy_name="test", trades=trades, equity_curve=[10_000, 10_150], final_balance=10_150)
    metrics = compute_metrics(result, initial_balance=10_000)
    assert metrics.profit_factor is None
    print("PASS: profit factor is None (not a crash) when there are no losing trades")


def test_max_drawdown_computed_from_equity_curve():
    # Equity rises to 10500, drops to 10000, matching a 4.76% drawdown from peak.
    equity_curve = [10_000, 10_200, 10_500, 10_300, 10_000, 10_100]
    result = BacktestResult(strategy_name="test", trades=[make_trade(100)],
                             equity_curve=equity_curve, final_balance=10_100)
    metrics = compute_metrics(result, initial_balance=10_000)
    expected_dd = (10_500 - 10_000) / 10_500 * 100
    assert abs(metrics.max_drawdown_pct - expected_dd) < 0.01, f"Expected {expected_dd:.2f}%, got {metrics.max_drawdown_pct:.2f}%"
    print(f"PASS: max drawdown correctly computed from equity curve peak ({metrics.max_drawdown_pct:.2f}%)")


if __name__ == "__main__":
    test_no_trades_gives_zeroed_metrics()
    test_win_rate_and_return_computed_correctly()
    test_profit_factor_none_when_no_losses()
    test_max_drawdown_computed_from_equity_curve()
    print("\nAll metrics tests passed.")
