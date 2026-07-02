"""
Symbol info lookup.

The risk manager needs `pip_value_per_lot` and `pip_size` to size
positions correctly (see risk/risk_manager.py). These vary by symbol
and by account currency — they must come from MT5 at runtime, never
be hardcoded, since a value baked in for EURUSD will silently be wrong
for USDJPY or a gold/index CFD.
"""

from dataclasses import dataclass

from data.mt5_connector import MT5Connector, MT5ConnectionError


@dataclass(frozen=True)
class SymbolInfo:
    symbol: str
    pip_size: float
    pip_value_per_lot: float
    digits: int
    min_lot: float
    max_lot: float
    lot_step: float
    spread_points: int


def get_symbol_info(connector: MT5Connector, symbol: str) -> SymbolInfo:
    """
    Fetch and normalize symbol info from MT5.

    Pip size convention: for 5-digit/3-digit broker quoting (the common
    case), 1 pip = 10 * point. For 4-digit/2-digit quoting, 1 pip =
    1 * point. We derive this from `digits` rather than assuming, since
    it differs by symbol and broker.
    """
    mt5 = connector.mt5
    info = mt5.symbol_info(symbol)
    if info is None:
        raise MT5ConnectionError(
            f"symbol_info returned None for '{symbol}' — check the symbol "
            f"name matches your broker's naming (e.g. 'EURUSD' vs 'EURUSD.m')."
        )

    # Ensure the symbol is visible/selected in Market Watch, or tick/rate
    # calls for it can silently fail.
    if not info.visible:
        if not mt5.symbol_select(symbol, True):
            raise MT5ConnectionError(f"Could not select '{symbol}' in Market Watch.")
        info = mt5.symbol_info(symbol)

    point = info.point
    digits = info.digits
    pip_size = point * 10 if digits in (3, 5) else point

    # trade_tick_value is the account-currency value of one tick move
    # for one standard lot. Convert to per-pip value using the pip/point
    # ratio derived above.
    ticks_per_pip = pip_size / point if point > 0 else 1
    pip_value_per_lot = info.trade_tick_value * ticks_per_pip

    return SymbolInfo(
        symbol=symbol,
        pip_size=pip_size,
        pip_value_per_lot=pip_value_per_lot,
        digits=digits,
        min_lot=info.volume_min,
        max_lot=info.volume_max,
        lot_step=info.volume_step,
        spread_points=info.spread,
    )
