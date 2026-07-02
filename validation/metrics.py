"""
Performance metrics computed from a BacktestResult.
"""

from dataclasses import dataclass

from execution.backtest_executor import BacktestResult


@dataclass
class PerformanceMetrics:
    strategy_name: str
    total_trades: int
    win_rate_pct: float
    total_return_pct: float
    max_drawdown_pct: float
    profit_factor: float | None  # None if there were no losing trades to divide by
    avg_win: float
    avg_loss: float
    blocked_signal_count: int


def compute_metrics(result: BacktestResult, initial_balance: float) -> PerformanceMetrics:
    trades = result.trades
    total_trades = len(trades)

    if total_trades == 0:
        return PerformanceMetrics(
            strategy_name=result.strategy_name,
            total_trades=0,
            win_rate_pct=0.0,
            total_return_pct=0.0,
            max_drawdown_pct=0.0,
            profit_factor=None,
            avg_win=0.0,
            avg_loss=0.0,
            blocked_signal_count=result.blocked_signal_count,
        )

    wins = [t for t in trades if t.pnl is not None and t.pnl > 0]
    losses = [t for t in trades if t.pnl is not None and t.pnl <= 0]

    win_rate = 100.0 * len(wins) / total_trades
    total_return_pct = 100.0 * (result.final_balance - initial_balance) / initial_balance

    gross_profit = sum(t.pnl for t in wins)
    gross_loss = abs(sum(t.pnl for t in losses))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else None

    avg_win = (gross_profit / len(wins)) if wins else 0.0
    avg_loss = (-gross_loss / len(losses)) if losses else 0.0

    max_drawdown_pct = _max_drawdown_pct(result.equity_curve, initial_balance)

    return PerformanceMetrics(
        strategy_name=result.strategy_name,
        total_trades=total_trades,
        win_rate_pct=win_rate,
        total_return_pct=total_return_pct,
        max_drawdown_pct=max_drawdown_pct,
        profit_factor=profit_factor,
        avg_win=avg_win,
        avg_loss=avg_loss,
        blocked_signal_count=result.blocked_signal_count,
    )


def _max_drawdown_pct(equity_curve: list[float], initial_balance: float) -> float:
    if not equity_curve:
        return 0.0
    peak = initial_balance
    max_dd = 0.0
    for equity in equity_curve:
        peak = max(peak, equity)
        dd = (peak - equity) / peak if peak > 0 else 0.0
        max_dd = max(max_dd, dd)
    return max_dd * 100.0
