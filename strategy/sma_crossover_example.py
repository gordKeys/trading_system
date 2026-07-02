"""
Example strategy: simple moving average crossover.

This exists to prove the Strategy interface end-to-end with something
simple and well-understood — NOT as a recommendation to trade this.
SMA crossovers are a textbook starting point, generally too slow/lossy
to be FTMO-challenge-viable on their own. Treat this as a template for
wiring in your actual trading hypothesis, not a candidate strategy.
"""

import pandas as pd

from strategy.base import Strategy, Signal, SignalType


class SMACrossoverStrategy(Strategy):
    name = "sma_crossover_example"

    def __init__(self, fast_period: int = 10, slow_period: int = 30, stop_pips: float = 20.0, pip_size: float = 0.0001):
        if fast_period >= slow_period:
            raise ValueError("fast_period must be less than slow_period")
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.stop_pips = stop_pips
        self.pip_size = pip_size

    def generate_signal(self, ohlc: pd.DataFrame) -> Signal:
        if len(ohlc) < self.slow_period + 1:
            return Signal(SignalType.FLAT, reason="not enough history yet")

        close = ohlc["close"]
        fast_ma = close.rolling(self.fast_period).mean()
        slow_ma = close.rolling(self.slow_period).mean()

        # Look at the last two bars to detect a crossover, not just
        # current relative position — otherwise every bar while fast > slow
        # would re-signal, instead of only the crossing bar.
        prev_fast, prev_slow = fast_ma.iloc[-2], slow_ma.iloc[-2]
        curr_fast, curr_slow = fast_ma.iloc[-1], slow_ma.iloc[-1]
        last_close = close.iloc[-1]

        crossed_up = prev_fast <= prev_slow and curr_fast > curr_slow
        crossed_down = prev_fast >= prev_slow and curr_fast < curr_slow

        if crossed_up:
            return Signal(
                signal_type=SignalType.BUY,
                entry_price=last_close,
                stop_loss_price=last_close - self.stop_pips * self.pip_size,
                reason=f"fast MA({self.fast_period}) crossed above slow MA({self.slow_period})",
            )
        if crossed_down:
            return Signal(
                signal_type=SignalType.SELL,
                entry_price=last_close,
                stop_loss_price=last_close + self.stop_pips * self.pip_size,
                reason=f"fast MA({self.fast_period}) crossed below slow MA({self.slow_period})",
            )

        return Signal(SignalType.FLAT, reason="no crossover on this bar")
