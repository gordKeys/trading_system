"""
Combo strategy: breakout confirmed by trend direction.

Hypothesis: an opening-range breakout is more likely to follow through
if the broader trend already agrees with the breakout direction —
i.e. only take breakouts that align with the prevailing trend, skip
counter-trend breakouts (which are more likely to be false/exhausted
moves that reverse).

This wraps two existing strategies rather than reimplementing their
logic, so any future fix to ORB or trend detection automatically
propagates here too.
"""

import pandas as pd

from strategy.base import Strategy, Signal, SignalType
from strategy.orb_breakout import OpeningRangeBreakout
from strategy.trend_following_ma import TrendFollowingMA


class TrendConfirmedBreakout(Strategy):
    name = "combo_trend_confirmed_breakout"

    def __init__(
        self,
        session_start_hour: int = 11,
        range_minutes: int = 30,
        bar_minutes: int = 15,
        trend_fast_period: int = 10,
        trend_slow_period: int = 30,
        stop_buffer_pips: float = 5.0,
        take_profit_r_multiple: float = 2.0,
        pip_size: float = 0.0001,
    ):
        self._orb = OpeningRangeBreakout(
            session_start_hour=session_start_hour,
            range_minutes=range_minutes,
            bar_minutes=bar_minutes,
            stop_buffer_pips=stop_buffer_pips,
            take_profit_r_multiple=take_profit_r_multiple,
            pip_size=pip_size,
        )
        self._trend_fast = trend_fast_period
        self._trend_slow = trend_slow_period
        self.pip_size = pip_size

    def generate_signal(self, ohlc: pd.DataFrame) -> Signal:
        orb_signal = self._orb.generate_signal(ohlc)
        if not orb_signal.is_actionable:
            return orb_signal

        if len(ohlc) < self._trend_slow + 1:
            return Signal(SignalType.FLAT, reason="breakout fired but not enough history for trend filter")

        close = ohlc["close"]
        fast_ma = close.rolling(self._trend_fast).mean().iloc[-1]
        slow_ma = close.rolling(self._trend_slow).mean().iloc[-1]

        trend_is_up = fast_ma > slow_ma
        trend_is_down = fast_ma < slow_ma

        if orb_signal.signal_type == SignalType.BUY and trend_is_up:
            return Signal(
                signal_type=SignalType.BUY,
                entry_price=orb_signal.entry_price,
                stop_loss_price=orb_signal.stop_loss_price,
                take_profit_price=orb_signal.take_profit_price,
                reason=f"{orb_signal.reason} + confirmed by uptrend",
            )
        if orb_signal.signal_type == SignalType.SELL and trend_is_down:
            return Signal(
                signal_type=SignalType.SELL,
                entry_price=orb_signal.entry_price,
                stop_loss_price=orb_signal.stop_loss_price,
                take_profit_price=orb_signal.take_profit_price,
                reason=f"{orb_signal.reason} + confirmed by downtrend",
            )

        return Signal(SignalType.FLAT, reason="breakout fired but trend disagreed — skipped")
