"""
General system settings — MT5 connection info and internal safety buffers.

Keep secrets (login, password, server) out of version control.
This reads them from environment variables — set those in a local
.env file (never commit it) or your OS environment directly.
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class MT5Settings:
    login: int = int(os.environ.get("MT5_LOGIN", "0"))
    password: str = os.environ.get("MT5_PASSWORD", "")
    server: str = os.environ.get("MT5_SERVER", "")
    # Path to terminal64.exe — only needed if MT5 isn't already running
    # or auto-detected. Leave blank to let the MetaTrader5 package find it.
    terminal_path: str = os.environ.get("MT5_TERMINAL_PATH", "")


@dataclass(frozen=True)
class SafetyBuffers:
    """
    Internal buffers that sit INSIDE FTMO's actual limits, so the bot
    stops itself before it ever gets close to a real breach.

    Never set these equal to FTMO's limits — a slippage event or a
    fast news candle can blow through the gap between "internal stop"
    and "FTMO's real limit" in seconds otherwise.
    """
    # Stop trading for the day once daily loss reaches this fraction
    # of FTMO's actual max daily loss (0.8 = stop at 80% of the limit).
    daily_loss_safety_fraction: float = 0.8

    # Stop trading entirely once total drawdown reaches this fraction
    # of FTMO's actual max drawdown.
    total_drawdown_safety_fraction: float = 0.8

    # Max risk per single trade, as a fraction of current account balance.
    max_risk_per_trade_pct: float = 0.005  # 0.5%

    # Max number of concurrent open positions.
    max_concurrent_positions: int = 1


MT5_SETTINGS = MT5Settings()
SAFETY_BUFFERS = SafetyBuffers()
