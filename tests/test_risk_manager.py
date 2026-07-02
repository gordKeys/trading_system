"""
Sanity tests for RiskManager. Run with:
    python -m tests.test_risk_manager

Not a full pytest suite — just enough to prove the core logic behaves
correctly on the scenarios that matter most: approaching daily loss
limit, approaching total drawdown, and normal position sizing.
"""

import sys
sys.path.insert(0, ".")

from risk.risk_manager import RiskManager, AccountState, TradeDecision


def test_normal_trade_allowed():
    rm = RiskManager()
    account = AccountState(
        initial_balance=10_000,
        current_balance=10_050,
        current_equity=10_050,
        daily_start_balance=10_000,
        open_positions_count=0,
    )
    allowed, reason = rm.can_open_trade(account)
    assert allowed, f"Expected trade allowed, got {reason}"
    print("PASS: normal trade allowed")


def test_daily_loss_blocks_trade():
    rm = RiskManager()
    # FTMO 10k: max daily loss = 5% = $500. Safety buffer 80% -> blocks at $400.
    account = AccountState(
        initial_balance=10_000,
        current_balance=9_580,  # down $420 today
        current_equity=9_580,
        daily_start_balance=10_000,
        open_positions_count=0,
    )
    allowed, reason = rm.can_open_trade(account)
    assert not allowed, "Expected trade blocked on daily loss"
    assert reason == TradeDecision.BLOCKED_DAILY_LOSS
    print("PASS: daily loss limit blocks trade")


def test_total_drawdown_blocks_trade():
    rm = RiskManager()
    # FTMO 10k: max total drawdown = 10% = $1000. Safety buffer 80% -> blocks at $800.
    account = AccountState(
        initial_balance=10_000,
        current_balance=9_150,  # down $850 total
        current_equity=9_150,
        daily_start_balance=9_500,
        open_positions_count=0,
    )
    allowed, reason = rm.can_open_trade(account)
    assert not allowed, "Expected trade blocked on total drawdown"
    assert reason == TradeDecision.BLOCKED_TOTAL_DRAWDOWN
    print("PASS: total drawdown limit blocks trade")


def test_max_positions_blocks_trade():
    rm = RiskManager()
    account = AccountState(
        initial_balance=10_000,
        current_balance=10_000,
        current_equity=10_000,
        daily_start_balance=10_000,
        open_positions_count=1,  # already at default max of 1
    )
    allowed, reason = rm.can_open_trade(account)
    assert not allowed
    assert reason == TradeDecision.BLOCKED_MAX_POSITIONS
    print("PASS: max concurrent positions blocks trade")


def test_position_sizing_respects_risk_cap():
    rm = RiskManager()
    account = AccountState(
        initial_balance=10_000,
        current_balance=10_000,
        current_equity=10_000,
        daily_start_balance=10_000,
    )
    # EURUSD-like: pip_value_per_lot ~ $10, pip_size 0.0001
    # 20 pip stop, risking 0.5% of 10,000 = $50
    lot_size = rm.calculate_position_size(
        account=account,
        entry_price=1.1000,
        stop_loss_price=1.0980,  # 20 pips away
        pip_value_per_lot=10.0,
        pip_size=0.0001,
    )
    # risk_amount = 50, risk_per_lot = 20 * 10 = 200 -> lot_size = 0.25
    assert abs(lot_size - 0.25) < 0.001, f"Expected 0.25 lots, got {lot_size}"
    print("PASS: position sizing correct (0.25 lots for $50 risk on 20 pip stop)")


def test_zero_stop_distance_returns_zero_size():
    rm = RiskManager()
    account = AccountState(
        initial_balance=10_000,
        current_balance=10_000,
        current_equity=10_000,
        daily_start_balance=10_000,
    )
    lot_size = rm.calculate_position_size(
        account=account,
        entry_price=1.1000,
        stop_loss_price=1.1000,  # same as entry — invalid
        pip_value_per_lot=10.0,
    )
    assert lot_size == 0.0
    print("PASS: zero stop distance correctly returns 0 lot size")


def test_daily_anchor_resets_on_new_day():
    from datetime import datetime, timezone
    rm = RiskManager()
    account = AccountState(
        initial_balance=10_000,
        current_balance=10_000,
        current_equity=10_000,
        daily_start_balance=10_000,
        last_daily_reset=datetime(2026, 7, 1, tzinfo=timezone.utc),
    )
    same_day = datetime(2026, 7, 1, 18, 0, tzinfo=timezone.utc)
    next_day = datetime(2026, 7, 2, 0, 5, tzinfo=timezone.utc)
    assert rm.should_reset_daily_anchor(account, same_day) is False
    assert rm.should_reset_daily_anchor(account, next_day) is True
    print("PASS: daily anchor reset triggers correctly on new server day")


if __name__ == "__main__":
    test_normal_trade_allowed()
    test_daily_loss_blocks_trade()
    test_total_drawdown_blocks_trade()
    test_max_positions_blocks_trade()
    test_position_sizing_respects_risk_cap()
    test_zero_stop_distance_returns_zero_size()
    test_daily_anchor_resets_on_new_day()
    print("\nAll risk manager sanity tests passed.")
