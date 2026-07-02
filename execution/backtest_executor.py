"""
Backtest executor.

Simulates a Strategy trading bar-by-bar over historical OHLC data,
using the SAME RiskManager that would run live — this is the point of
the whole layered architecture: the backtest isn't a separate simpler
model of risk, it's the real risk logic replayed against history.

Simplifications (documented, not hidden):
  - Single position at a time (matches SafetyBuffers.max_concurrent_positions
    default of 1).
  - Fill price = signal's entry_price (no slippage/spread modeling yet).
  - Exit ONLY via stop-loss or take-profit hit within a bar's high/low
    range — no trailing stops, no manual exit logic yet.
  - If both stop and take-profit fall within the same bar's range, we
    conservatively assume the STOP was hit first (worst case), never
    the reverse — this avoids overstating performance on volatile bars.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

import pandas as pd

from strategy.base import Strategy, SignalType
from risk.risk_manager import RiskManager, AccountState, TradeDecision


class ExitReason(Enum):
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    END_OF_DATA = "end_of_data"  # position still open when backtest data runs out


@dataclass
class Trade:
    direction: SignalType
    entry_time: datetime
    entry_price: float
    stop_loss_price: float
    take_profit_price: float | None
    lot_size: float
    exit_time: datetime | None = None
    exit_price: float | None = None
    exit_reason: ExitReason | None = None
    pnl: float | None = None


@dataclass
class BacktestResult:
    strategy_name: str
    trades: list[Trade] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)
    final_balance: float = 0.0
    blocked_signal_count: int = 0  # signals the risk manager refused (limit hit)


def run_backtest(
    strategy: Strategy,
    ohlc: pd.DataFrame,
    initial_balance: float,
    pip_value_per_lot: float,
    pip_size: float = 0.0001,
    risk_manager: RiskManager | None = None,
    warmup_bars: int = 50,
) -> BacktestResult:
    """
    ohlc: full historical DataFrame, columns [open, high, low, close, ...],
    indexed by time, oldest first.

    warmup_bars: how many initial bars to skip before allowing signals,
    so strategies needing lookback (e.g. a 30-period MA) don't fire on
    incomplete data. Must be >= whatever the strategy itself needs.

    Strategy.generate_signal is called on ohlc.iloc[:i+1] at each step —
    NEVER on the full DataFrame — so a strategy has no way to see future
    bars, matching how it would behave live.
    """
    rm = risk_manager or RiskManager()
    result = BacktestResult(strategy_name=strategy.name)

    account = AccountState(
        initial_balance=initial_balance,
        current_balance=initial_balance,
        current_equity=initial_balance,
        daily_start_balance=initial_balance,
        open_positions_count=0,
        last_daily_reset=ohlc.index[0].to_pydatetime() if len(ohlc) else datetime.now(timezone.utc),
    )

    open_trade: Trade | None = None

    for i in range(warmup_bars, len(ohlc)):
        bar = ohlc.iloc[i]
        bar_time = ohlc.index[i]

        # Daily anchor reset check
        bar_time_dt = bar_time.to_pydatetime().replace(tzinfo=timezone.utc)
        if rm.should_reset_daily_anchor(account, bar_time_dt):
            account.daily_start_balance = account.current_balance
            account.last_daily_reset = bar_time_dt

        # --- Manage an open position first: check stop/take-profit against this bar ---
        if open_trade is not None:
            closed_trade, still_open = _check_exit(open_trade, bar, bar_time)
            if closed_trade is not None:
                closed_trade.pnl = _calc_pnl(closed_trade, pip_value_per_lot, pip_size)
                account.current_balance += closed_trade.pnl
                account.current_equity = account.current_balance
                account.open_positions_count = 0
                result.trades.append(closed_trade)
                open_trade = None
            else:
                open_trade = still_open

        # --- Only look for a new signal if flat ---
        if open_trade is None:
            history_slice = ohlc.iloc[: i + 1]
            signal = strategy.generate_signal(history_slice)

            if signal.is_actionable:
                allowed, decision = rm.can_open_trade(account)
                if not allowed:
                    result.blocked_signal_count += 1
                else:
                    lot_size = rm.calculate_position_size(
                        account=account,
                        entry_price=signal.entry_price,
                        stop_loss_price=signal.stop_loss_price,
                        pip_value_per_lot=pip_value_per_lot,
                        pip_size=pip_size,
                    )
                    if lot_size > 0:
                        open_trade = Trade(
                            direction=signal.signal_type,
                            entry_time=bar_time,
                            entry_price=signal.entry_price,
                            stop_loss_price=signal.stop_loss_price,
                            take_profit_price=signal.take_profit_price,
                            lot_size=lot_size,
                        )
                        account.open_positions_count = 1

        result.equity_curve.append(account.current_equity)

    # Close out any still-open trade at the last available price
    if open_trade is not None:
        last_bar = ohlc.iloc[-1]
        open_trade.exit_time = ohlc.index[-1]
        open_trade.exit_price = last_bar["close"]
        open_trade.exit_reason = ExitReason.END_OF_DATA
        open_trade.pnl = _calc_pnl(open_trade, pip_value_per_lot, pip_size)
        account.current_balance += open_trade.pnl
        account.current_equity = account.current_balance
        result.trades.append(open_trade)

    result.final_balance = account.current_balance
    return result


def _calc_pnl(trade: Trade, pip_value_per_lot: float, pip_size: float) -> float:
    direction_mult = 1 if trade.direction == SignalType.BUY else -1
    price_diff = (trade.exit_price - trade.entry_price) * direction_mult
    pips = price_diff / pip_size
    return pips * pip_value_per_lot * trade.lot_size


def _check_exit(trade: Trade, bar: pd.Series, bar_time) -> tuple[Trade | None, Trade | None]:
    """
    Returns (closed_trade, None) if the trade's stop or take-profit was
    hit on this bar, or (None, trade) if it's still open and unchanged.
    """
    high, low = bar["high"], bar["low"]
    hit_stop = False
    hit_tp = False

    if trade.direction == SignalType.BUY:
        if low <= trade.stop_loss_price:
            hit_stop = True
        if trade.take_profit_price is not None and high >= trade.take_profit_price:
            hit_tp = True
    else:  # SELL
        if high >= trade.stop_loss_price:
            hit_stop = True
        if trade.take_profit_price is not None and low <= trade.take_profit_price:
            hit_tp = True

    if not hit_stop and not hit_tp:
        return None, trade

    # Conservative assumption: if both could have been hit in this bar,
    # the stop is assumed to have triggered first.
    if hit_stop:
        trade.exit_price = trade.stop_loss_price
        trade.exit_reason = ExitReason.STOP_LOSS
    else:
        trade.exit_price = trade.take_profit_price
        trade.exit_reason = ExitReason.TAKE_PROFIT

    trade.exit_time = bar_time
    return trade, None
