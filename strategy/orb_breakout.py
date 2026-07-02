"""
Opening-range breakout strategy.

Hypothesis: the first N minutes of a trading session establish a
range; a decisive break of that range tends to continue in the
breakout direction for the rest of the session (institutional order
flow arriving at session open).

Uses broker-server timestamps directly (not UTC) for simplicity — the
range window is defined in broker-server-clock hours. Convert your
desired real-world session time (e.g. "London opens 08:00 UTC") to
broker-server-clock hours via data/broker_time.py::utc_to_broker_time
before configuring `session_start_hour` here.

NOTE — deliberate exception to Strategy's stateless-across-calls
guidance in strategy/base.py: this strategy tracks "have I already
traded today's session" as instance state, since that's genuinely
part of the trading rule (max one attempt per session), not a hidden
side-effect. Always construct a FRESH instance per backtest run — never
reuse one instance across two different runs/date ranges, or stale
day-state will leak between them.
"""

from dataclasses import dataclass

import pandas as pd

from strategy.base import Strategy, Signal, SignalType


@dataclass
class _DayState:
    date: object = None
    range_high: float | None = None
    range_low: float | None = None
    range_locked: bool = False
    traded_today: bool = False


class OpeningRangeBreakout(Strategy):
    name = "orb_breakout"

    def __init__(
        self,
        session_start_hour: int = 11,   # broker-server-clock hour, e.g. 11 = 08:00 UTC at +3 offset
        range_minutes: int = 30,
        bar_minutes: int = 15,
        stop_buffer_pips: float = 5.0,
        take_profit_r_multiple: float = 2.0,
        pip_size: float = 0.0001,
    ):
        self.session_start_hour = session_start_hour
        self.range_bars = max(1, range_minutes // bar_minutes)
        self.stop_buffer_pips = stop_buffer_pips
        self.take_profit_r_multiple = take_profit_r_multiple
        self.pip_size = pip_size
        self._state = _DayState()

    def generate_signal(self, ohlc: pd.DataFrame) -> Signal:
        if len(ohlc) < self.range_bars + 1:
            return Signal(SignalType.FLAT, reason="not enough history")

        now = ohlc.index[-1]
        today = now.date()

        if self._state.date != today:
            self._state = _DayState(date=today)

        if self._state.traded_today:
            return Signal(SignalType.FLAT, reason="already traded the session today")

        session_bars = ohlc[
            (ohlc.index.date == today) & (ohlc.index.hour == self.session_start_hour)
        ]

        if len(session_bars) < self.range_bars:
            return Signal(SignalType.FLAT, reason="session range not fully formed yet")

        if not self._state.range_locked:
            range_window = session_bars.iloc[: self.range_bars]
            if len(range_window) < self.range_bars:
                return Signal(SignalType.FLAT, reason="range window incomplete")
            self._state.range_high = range_window["high"].max()
            self._state.range_low = range_window["low"].min()
            self._state.range_locked = True

        last_bar = ohlc.iloc[-1]
        if last_bar.name <= session_bars.iloc[self.range_bars - 1].name:
            # Still inside the range-forming window itself — don't trade the range bars.
            return Signal(SignalType.FLAT, reason="still forming the opening range")

        close = last_bar["close"]
        range_size = self._state.range_high - self._state.range_low
        if range_size <= 0:
            return Signal(SignalType.FLAT, reason="degenerate zero-width range")

        stop_buffer = self.stop_buffer_pips * self.pip_size

        if close > self._state.range_high:
            entry = close
            stop = self._state.range_low - stop_buffer
            risk = entry - stop
            take_profit = entry + risk * self.take_profit_r_multiple
            self._state.traded_today = True
            return Signal(
                signal_type=SignalType.BUY,
                entry_price=entry,
                stop_loss_price=stop,
                take_profit_price=take_profit,
                reason=f"broke above opening range high {self._state.range_high:.5f}",
            )

        if close < self._state.range_low:
            entry = close
            stop = self._state.range_high + stop_buffer
            risk = stop - entry
            take_profit = entry - risk * self.take_profit_r_multiple
            self._state.traded_today = True
            return Signal(
                signal_type=SignalType.SELL,
                entry_price=entry,
                stop_loss_price=stop,
                take_profit_price=take_profit,
                reason=f"broke below opening range low {self._state.range_low:.5f}",
            )

        return Signal(SignalType.FLAT, reason="price still inside opening range")
