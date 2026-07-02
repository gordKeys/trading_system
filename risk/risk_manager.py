"""
Risk & money management layer.

Sits between strategy signals and execution. Its jobs:

1. Track account state (balance, equity, daily starting balance) needed
   to evaluate FTMO's rules.
2. Decide whether a NEW trade is allowed right now at all.
3. Calculate a safe position size for a trade that IS allowed.

Design principle: this layer knows nothing about *why* a strategy wants
to trade. It only ever sees "strategy wants to open X at price P with
stop-loss at S" and answers "yes/no, and if yes, what size". This
isolation is deliberate — the risk layer must be testable and auditable
completely independently of any particular strategy's logic.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from config.ftmo_rules import FTMORules, FTMO_10K_RULES
from config.settings import SafetyBuffers, SAFETY_BUFFERS


class TradeDecision(Enum):
    ALLOWED = "allowed"
    BLOCKED_DAILY_LOSS = "blocked_daily_loss_limit"
    BLOCKED_TOTAL_DRAWDOWN = "blocked_total_drawdown_limit"
    BLOCKED_MAX_POSITIONS = "blocked_max_concurrent_positions"
    BLOCKED_INVALID_STOP = "blocked_invalid_stop_loss"


@dataclass
class AccountState:
    """
    Snapshot of account state needed for risk decisions.
    In live trading this gets refreshed from MT5 each cycle.
    In backtesting, the backtest executor updates this directly.
    """
    initial_balance: float
    current_balance: float
    current_equity: float
    daily_start_balance: float  # balance at start of current trading day (server time)
    open_positions_count: int = 0
    last_daily_reset: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class RiskManager:
    def __init__(
        self,
        ftmo_rules: FTMORules = FTMO_10K_RULES,
        safety_buffers: SafetyBuffers = SAFETY_BUFFERS,
    ):
        self.rules = ftmo_rules
        self.buffers = safety_buffers

    # ------------------------------------------------------------------
    # Trade permission checks
    # ------------------------------------------------------------------

    def can_open_trade(self, account: AccountState) -> tuple[bool, TradeDecision]:
        """
        The gate every trade must pass through before execution.
        Checks are ordered from most to least severe consequence.
        """
        # 1. Total drawdown (most severe — this ends the challenge)
        drawdown_limit = self.rules.max_total_drawdown_amount * self.buffers.total_drawdown_safety_fraction
        current_drawdown = account.initial_balance - min(account.current_equity, account.current_balance)
        if current_drawdown >= drawdown_limit:
            return False, TradeDecision.BLOCKED_TOTAL_DRAWDOWN

        # 2. Daily loss
        daily_loss_limit = self.rules.max_daily_loss_amount * self.buffers.daily_loss_safety_fraction
        daily_loss = account.daily_start_balance - min(account.current_equity, account.current_balance)
        if daily_loss >= daily_loss_limit:
            return False, TradeDecision.BLOCKED_DAILY_LOSS

        # 3. Concurrent position limit
        if account.open_positions_count >= self.buffers.max_concurrent_positions:
            return False, TradeDecision.BLOCKED_MAX_POSITIONS

        return True, TradeDecision.ALLOWED

    # ------------------------------------------------------------------
    # Position sizing
    # ------------------------------------------------------------------

    def calculate_position_size(
        self,
        account: AccountState,
        entry_price: float,
        stop_loss_price: float,
        pip_value_per_lot: float,
        pip_size: float = 0.0001,
    ) -> float:
        """
        Size the trade so a stop-loss hit risks no more than
        `max_risk_per_trade_pct` of current account balance.

        pip_value_per_lot: monetary value of a 1-pip move for 1.0
        standard lot of the traded symbol. This varies by pair and
        account currency — pull it from MT5's symbol_info at runtime,
        never hardcode it.

        Returns 0.0 if the stop distance is invalid (zero, or on the
        wrong side of entry) — the caller must treat that as "do not
        place this trade", not as "use the minimum lot size".
        """
        stop_distance = abs(entry_price - stop_loss_price)
        if stop_distance <= 0:
            return 0.0

        stop_distance_pips = stop_distance / pip_size
        if stop_distance_pips <= 0:
            return 0.0

        risk_amount = account.current_balance * self.buffers.max_risk_per_trade_pct
        risk_per_lot = stop_distance_pips * pip_value_per_lot

        if risk_per_lot <= 0:
            return 0.0

        lot_size = risk_amount / risk_per_lot

        # Round DOWN to 2 decimals (standard MT5 lot precision).
        # Rounding down (never up) is deliberate — err toward less risk.
        # Small epsilon guards against float imprecision (e.g. 0.25
        # arriving as 0.24999999999997) causing an unwarranted extra
        # step down.
        epsilon = 1e-9
        lot_size = int((lot_size + epsilon) * 100) / 100

        return max(lot_size, 0.0)

    # ------------------------------------------------------------------
    # Daily state management
    # ------------------------------------------------------------------

    def should_reset_daily_anchor(self, account: AccountState, now: datetime) -> bool:
        """
        FTMO resets the daily loss anchor at midnight server time
        (typically CET/CEST). Returns True if a reset is due.

        NOTE: confirm your specific FTMO server's reset time on your
        dashboard — do not assume UTC.
        """
        last_reset_date = account.last_daily_reset.date()
        now_date = now.date()
        return now_date > last_reset_date
