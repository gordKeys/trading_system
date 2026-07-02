"""
Mean-reversion strategy: RSI extremes with a range filter.

Hypothesis: in a non-trending market, price oscillates around a mean
and RSI extremes mark exhaustion points that tend to revert. The ADX-
style trend filter is deliberately left out here for simplicity — this
means the strategy WILL take losing trades if it fires during a strong
trend (RSI can stay "oversold"/"overbought" for a long time in a
trend). That's expected and exactly the kind of failure mode the
leaderboard/backtest should reveal, not something to silently patch
around before we have data showing whether it matters.
"""

import pandas as pd

from strategy.base import Strategy, Signal, SignalType


def _rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    # Standard RSI formula divides by avg_loss, which is undefined at
    # zero. The naive fix of filling NaN with a flat "50" is WRONG for
    # the all-gains case (avg_loss == 0, avg_gain > 0) — that's the
    # maximally bullish reading and must be 100, not neutral. Handle
    # all three edge cases explicitly instead of relying on a single
    # fillna to paper over them.
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    rsi = 100 - (100 / (1 + rs))

    rsi = rsi.where(avg_loss != 0, other=pd.NA)  # clear the divide-by-zero NaNs first
    all_gains_mask = (avg_loss == 0) & (avg_gain > 0)
    no_movement_mask = (avg_loss == 0) & (avg_gain == 0)
    rsi = rsi.mask(all_gains_mask, 100.0)
    rsi = rsi.mask(no_movement_mask, 50.0)

    return rsi.astype(float)


class MeanReversionRSI(Strategy):
    name = "mean_reversion_rsi"

    def __init__(
        self,
        rsi_period: int = 14,
        oversold: float = 30.0,
        overbought: float = 70.0,
        stop_pips: float = 20.0,
        take_profit_r_multiple: float = 1.5,
        pip_size: float = 0.0001,
    ):
        self.rsi_period = rsi_period
        self.oversold = oversold
        self.overbought = overbought
        self.stop_pips = stop_pips
        self.take_profit_r_multiple = take_profit_r_multiple
        self.pip_size = pip_size

    def generate_signal(self, ohlc: pd.DataFrame) -> Signal:
        min_bars = self.rsi_period + 2
        if len(ohlc) < min_bars:
            return Signal(SignalType.FLAT, reason="not enough history yet")

        close = ohlc["close"]
        rsi = _rsi(close, self.rsi_period)

        prev_rsi = rsi.iloc[-2]
        curr_rsi = rsi.iloc[-1]
        last_close = close.iloc[-1]
        stop_dist = self.stop_pips * self.pip_size

        # Signal on the crossing BACK above/below the threshold (i.e. the
        # reversal starting), not on every bar RSI happens to sit past it.
        crossing_up_from_oversold = prev_rsi <= self.oversold and curr_rsi > self.oversold
        crossing_down_from_overbought = prev_rsi >= self.overbought and curr_rsi < self.overbought

        if crossing_up_from_oversold:
            return Signal(
                signal_type=SignalType.BUY,
                entry_price=last_close,
                stop_loss_price=last_close - stop_dist,
                take_profit_price=last_close + stop_dist * self.take_profit_r_multiple,
                reason=f"RSI reverted up out of oversold ({prev_rsi:.1f} -> {curr_rsi:.1f})",
            )
        if crossing_down_from_overbought:
            return Signal(
                signal_type=SignalType.SELL,
                entry_price=last_close,
                stop_loss_price=last_close + stop_dist,
                take_profit_price=last_close - stop_dist * self.take_profit_r_multiple,
                reason=f"RSI reverted down out of overbought ({prev_rsi:.1f} -> {curr_rsi:.1f})",
            )

        return Signal(SignalType.FLAT, reason=f"RSI {curr_rsi:.1f} — no reversal signal")
