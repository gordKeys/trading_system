"""
FTMO Challenge rules — single source of truth.

Every number here is a hard constraint from FTMO's challenge terms.
Nothing downstream (risk, execution, orchestration) should hardcode
these values directly — always import from here.

IMPORTANT: Verify these against your actual FTMO account dashboard
before going live. FTMO adjusts terms by account type, and this file
must match your specific challenge exactly.

Confirmed for this build (FTMO Standard, $10k):
  - Profit target: 10% (Phase 1), 5% (Phase 2 / Verification)
  - Max daily loss: 5%
  - Max total drawdown: 10%, STATIC from initial balance
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class FTMORules:
    # --- Account size ---
    account_size: float = 10_000.0

    # --- Loss limits (fraction of account_size, e.g. 0.05 = 5%) ---
    max_daily_loss_pct: float = 0.05
    max_total_drawdown_pct: float = 0.10

    # --- Profit targets ---
    phase1_profit_target_pct: float = 0.10
    phase2_profit_target_pct: float = 0.05

    # --- Trading day requirements ---
    min_trading_days: int = 4

    # --- Daily loss anchor ---
    # FTMO calculates daily loss from the previous day's END-OF-DAY
    # balance (server time, typically midnight CET/CEST) — NOT from
    # an equity peak during the day.
    daily_loss_anchor: str = "previous_day_balance"

    # --- Max drawdown anchor ---
    # Confirmed static: measured from the account's INITIAL balance,
    # not a trailing high-water mark.
    max_drawdown_anchor: str = "initial_balance"

    # --- Derived absolute values (computed, never hand-entered) ---
    @property
    def max_daily_loss_amount(self) -> float:
        return self.account_size * self.max_daily_loss_pct

    @property
    def max_total_drawdown_amount(self) -> float:
        return self.account_size * self.max_total_drawdown_pct

    @property
    def phase1_profit_target_amount(self) -> float:
        return self.account_size * self.phase1_profit_target_pct

    @property
    def phase2_profit_target_amount(self) -> float:
        return self.account_size * self.phase2_profit_target_pct


# Single shared instance — import this, don't instantiate your own
# unless you're testing a different account size.
FTMO_10K_RULES = FTMORules(account_size=10_000.0)
