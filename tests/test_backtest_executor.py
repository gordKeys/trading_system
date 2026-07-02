"""
Tests for the backtest executor, using tiny deterministic synthetic
price paths and a fake strategy that fires signals on command — this
isolates the EXECUTION logic (fills, stop/TP checks, PnL, risk gating)
from any real strategy's signal logic.

Run with: python -m tests.test_backtest_executor
"""

import sys
sys.path.insert(0, ".")

import pandas as pd

from strategy.base import Strategy, Signal, SignalType
from risk.risk_manager import RiskManager
from execution.backtest_executor import run_backtest, ExitReason


def make_ohlc(bars: list[dict]) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=len(bars), freq="15min")
    return pd.DataFrame(bars, index=idx)


class FireOnceStrategy(Strategy):
    """Fires a single fixed signal on the first bar it's allowed to act on, then goes flat forever."""
    name = "fire_once_test_strategy"

    def __init__(self, signal: Signal):
        self._signal = signal
        self._fired = False

    def generate_signal(self, ohlc: pd.DataFrame) -> Signal:
        if not self._fired:
            self._fired = True
            return self._signal
        return Signal(SignalType.FLAT)


def test_take_profit_hit_produces_positive_pnl():
    strat = FireOnceStrategy(Signal(
        signal_type=SignalType.BUY,
        entry_price=1.1000,
        stop_loss_price=1.0980,   # 20 pips
        take_profit_price=1.1040,  # 40 pips
    ))
    bars = [{"open": 1.1000, "high": 1.1005, "low": 1.0995, "close": 1.1000}] * 5
    bars.append({"open": 1.1000, "high": 1.1045, "low": 1.0995, "close": 1.1040})  # TP hit
    bars += [{"open": 1.1040, "high": 1.1045, "low": 1.1035, "close": 1.1040}] * 3
    df = make_ohlc(bars)

    result = run_backtest(strat, df, initial_balance=10_000, pip_value_per_lot=10.0, warmup_bars=0)
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.exit_reason == ExitReason.TAKE_PROFIT
    assert trade.pnl > 0
    assert result.final_balance > 10_000
    print(f"PASS: TP hit produces positive PnL (pnl={trade.pnl:.2f}, final_balance={result.final_balance:.2f})")


def test_stop_loss_hit_produces_negative_pnl():
    strat = FireOnceStrategy(Signal(
        signal_type=SignalType.BUY,
        entry_price=1.1000,
        stop_loss_price=1.0980,
        take_profit_price=1.1040,
    ))
    bars = [{"open": 1.1000, "high": 1.1005, "low": 1.0995, "close": 1.1000}] * 5
    bars.append({"open": 1.1000, "high": 1.1005, "low": 1.0975, "close": 1.0980})  # SL hit
    df = make_ohlc(bars)

    result = run_backtest(strat, df, initial_balance=10_000, pip_value_per_lot=10.0, warmup_bars=0)
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.exit_reason == ExitReason.STOP_LOSS
    assert trade.pnl < 0
    assert result.final_balance < 10_000
    print(f"PASS: SL hit produces negative PnL (pnl={trade.pnl:.2f}, final_balance={result.final_balance:.2f})")


def test_both_stop_and_tp_in_same_bar_assumes_stop_first():
    # Conservative assumption: a huge-range bar that touches both stop
    # and take-profit should be scored as a LOSS, not a win.
    strat = FireOnceStrategy(Signal(
        signal_type=SignalType.BUY,
        entry_price=1.1000,
        stop_loss_price=1.0980,
        take_profit_price=1.1040,
    ))
    bars = [{"open": 1.1000, "high": 1.1005, "low": 1.0995, "close": 1.1000}] * 5
    bars.append({"open": 1.1000, "high": 1.1050, "low": 1.0970, "close": 1.1010})  # both touched
    df = make_ohlc(bars)

    result = run_backtest(strat, df, initial_balance=10_000, pip_value_per_lot=10.0, warmup_bars=0)
    trade = result.trades[0]
    assert trade.exit_reason == ExitReason.STOP_LOSS
    print("PASS: bar touching both stop and TP is conservatively scored as stop-loss")


def test_no_signal_produces_no_trades():
    class AlwaysFlat(Strategy):
        name = "always_flat"
        def generate_signal(self, ohlc):
            return Signal(SignalType.FLAT)

    bars = [{"open": 1.1000, "high": 1.1005, "low": 1.0995, "close": 1.1000}] * 10
    df = make_ohlc(bars)
    result = run_backtest(AlwaysFlat(), df, initial_balance=10_000, pip_value_per_lot=10.0, warmup_bars=0)
    assert len(result.trades) == 0
    assert result.final_balance == 10_000
    print("PASS: a strategy that never signals produces zero trades, balance unchanged")


def test_risk_manager_blocks_new_trades_after_daily_loss_breach():
    """
    A strategy that always tries to re-enter the moment it's flat, paired
    with a RiskManager configured (for test purposes only) to risk a large
    enough fraction per trade that a single stop-out breaches the daily
    loss safety buffer. The second attempt must be blocked by the real
    RiskManager, not silently allowed.
    """
    from config.settings import SafetyBuffers

    class AlwaysTryBuyStrategy(Strategy):
        name = "always_try_buy_test"
        def generate_signal(self, ohlc):
            return Signal(SignalType.BUY, entry_price=1.1000, stop_loss_price=1.0500, take_profit_price=None)

    bars = [{"open": 1.1000, "high": 1.1005, "low": 1.0995, "close": 1.1000}]
    bars.append({"open": 1.1000, "high": 1.1005, "low": 1.0400, "close": 1.0500})  # huge SL hit -> big loss
    bars += [{"open": 1.0500, "high": 1.0505, "low": 1.0495, "close": 1.0500}] * 5
    df = make_ohlc(bars)

    # Oversized risk-per-trade so ONE loss breaches the daily safety
    # buffer ($400 for a $10k account) — isolates the risk-gating wiring
    # from needing many trades to accumulate a breach.
    aggressive_buffers = SafetyBuffers(
        daily_loss_safety_fraction=0.8,
        total_drawdown_safety_fraction=0.8,
        max_risk_per_trade_pct=0.5,
        max_concurrent_positions=1,
    )
    rm = RiskManager(safety_buffers=aggressive_buffers)
    result = run_backtest(AlwaysTryBuyStrategy(), df, initial_balance=10_000, pip_value_per_lot=10.0,
                           risk_manager=rm, warmup_bars=0)

    assert len(result.trades) == 1, f"Expected exactly 1 trade to open before blocking, got {len(result.trades)}"
    assert result.blocked_signal_count > 0, "Expected the risk manager to block further signals after the breach"
    print(f"PASS: risk manager blocks further trades after safety buffer breach "
          f"(1 trade opened, {result.blocked_signal_count} subsequent signals blocked)")


if __name__ == "__main__":
    test_take_profit_hit_produces_positive_pnl()
    test_stop_loss_hit_produces_negative_pnl()
    test_both_stop_and_tp_in_same_bar_assumes_stop_first()
    test_no_signal_produces_no_trades()
    test_risk_manager_blocks_new_trades_after_daily_loss_breach()
    print("\nAll backtest executor tests passed.")
