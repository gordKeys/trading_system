"""
Trend-following strategy: MA crossover confirmed by trend slope.

Hypothesis: a fast MA crossing the slow MA marks a trend shift, but
crossovers in a flat/choppy market are noise. Requiring the slow MA
itself to be sloping in the trade direction filters out crossovers
that happen while the broader trend is flat — a common cheap filter
for the classic crossover strategy's biggest weakness (whipsaws).
"""

import pandas as pd

from strategy.base import Strategy, Signal, SignalType


class TrendFollowingMA(Strategy):
    name = "trend_following_ma"

    def __init__(
        self,
        fast_period: int = 10,
        slow_period: int = 30,
        slope_lookback: int = 5,
        stop_pips: float = 25.0,
        take_profit_r_multiple: float = 2.0,
        pip_size: float = 0.0001,
    ):
        if fast_period >= slow_period:
            raise ValueError("fast_period must be less than slow_period")
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.slope_lookback = slope_lookback
        self.stop_pips = stop_pips
        self.take_profit_r_multiple = take_profit_r_multiple
        self.pip_size = pip_size

    def generate_signal(self, ohlc: pd.DataFrame) -> Signal:
        min_bars = self.slow_period + self.slope_lookback + 1
        if len(ohlc) < min_bars:
            return Signal(SignalType.FLAT, reason="not enough history yet")

        close = ohlc["close"]
        fast_ma = close.rolling(self.fast_period).mean()
        slow_ma = close.rolling(self.slow_period).mean()

        prev_fast, prev_slow = fast_ma.iloc[-2], slow_ma.iloc[-2]
        curr_fast, curr_slow = fast_ma.iloc[-1], slow_ma.iloc[-1]
        last_close = close.iloc[-1]

        slow_slope = slow_ma.iloc[-1] - slow_ma.iloc[-1 - self.slope_lookback]

        crossed_up = prev_fast <= prev_slow and curr_fast > curr_slow
        crossed_down = prev_fast >= prev_slow and curr_fast < curr_slow

        stop_dist = self.stop_pips * self.pip_size

        if crossed_up and slow_slope > 0:
            stop = last_close - stop_dist
            return Signal(
                signal_type=SignalType.BUY,
                entry_price=last_close,
                stop_loss_price=stop,
                take_profit_price=last_close + stop_dist * self.take_profit_r_multiple,
                reason="bullish MA crossover confirmed by rising slow MA slope",
            )
        if crossed_down and slow_slope < 0:
            stop = last_close + stop_dist
            return Signal(
                signal_type=SignalType.SELL,
                entry_price=last_close,
                stop_loss_price=stop,
                take_profit_price=last_close - stop_dist * self.take_profit_r_multiple,
                reason="bearish MA crossover confirmed by falling slow MA slope",
            )

        return Signal(SignalType.FLAT, reason="no confirmed crossover")
