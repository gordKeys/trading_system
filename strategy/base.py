"""
Strategy layer base interface.

A strategy's ONLY job: given price history, decide whether there's a
tradeable setup right now, and if so, at what price and with what
stop-loss. It knows NOTHING about account size, risk-per-trade, FTMO
rules, or how the order actually gets placed — that separation is
what lets us swap strategies freely, backtest them identically to how
they'd run live, and unit-test signal logic with zero MT5 dependency.

Every strategy implementation should be:
  - Pure: same input DataFrame always produces the same signal.
  - Stateless across calls where possible (if a strategy needs to
    remember something between bars — e.g. "have I already traded the
    London open today" — that state should be explicit and passed in,
    not hidden as instance mutation that backtest and live could
    diverge on).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

import pandas as pd


class SignalType(Enum):
    BUY = "buy"
    SELL = "sell"
    FLAT = "flat"  # no setup right now — do nothing


@dataclass(frozen=True)
class Signal:
    signal_type: SignalType
    entry_price: float | None = None
    stop_loss_price: float | None = None
    take_profit_price: float | None = None
    reason: str = ""  # short human-readable note, useful in logs/backtest reports

    @property
    def is_actionable(self) -> bool:
        return self.signal_type != SignalType.FLAT


class Strategy(ABC):
    """
    Base class every strategy implements. `name` should be unique and
    stable — it's used as the key in leaderboard/validation reports.
    """

    name: str = "unnamed_strategy"

    @abstractmethod
    def generate_signal(self, ohlc: pd.DataFrame) -> Signal:
        """
        ohlc: DataFrame indexed by time, columns at minimum
        [open, high, low, close] — see data/market_data.py for the
        exact schema this comes from in production.

        Must look ONLY at data up to and including the last row —
        never at future bars. This is what makes a strategy safe to
        run identically in backtest and live. The backtest engine is
        responsible for enforcing this by only ever passing the slice
        of history "known so far" at each simulated point in time.

        Returns a Signal. Return SignalType.FLAT when there's no setup.
        """
        raise NotImplementedError
