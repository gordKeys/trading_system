"""
MT5 connection lifecycle management.

The `MetaTrader5` package only works on Windows with a running MT5
terminal — it can't be installed or exercised in most dev/CI sandboxes.
To keep this testable anyway, `MT5Connector` accepts the mt5 module as
a constructor argument instead of importing it directly at module load
time. In production you don't pass anything and it lazily imports the
real package; in tests you pass a mock/fake object that mimics the
handful of functions we actually use.

This is the ONLY module that should ever import MetaTrader5 directly
elsewhere in the codebase — everything else goes through this class
or through data/market_data.py, which takes a connected MT5Connector.
"""

from dataclasses import dataclass

from config.settings import MT5Settings, MT5_SETTINGS


class MT5ConnectionError(RuntimeError):
    """Raised when MT5 initialization or login fails."""


@dataclass
class ConnectionStatus:
    connected: bool
    account_login: int | None = None
    server: str | None = None
    message: str = ""


class MT5Connector:
    def __init__(self, settings: MT5Settings = MT5_SETTINGS, mt5_module=None):
        """
        settings: MT5 login/server/path config.
        mt5_module: inject a fake/mock here for testing. Leave None to
        use the real `MetaTrader5` package (requires Windows + terminal).
        """
        self.settings = settings
        self._mt5 = mt5_module
        self._connected = False

    @property
    def mt5(self):
        """Lazily import the real MetaTrader5 package on first use."""
        if self._mt5 is None:
            try:
                import MetaTrader5 as mt5  # noqa: N813
            except ImportError as e:
                raise MT5ConnectionError(
                    "MetaTrader5 package not available. This only installs "
                    "and runs on Windows with the MT5 terminal present. "
                    "Run this on your machine with the demo account, not "
                    "in a Linux sandbox."
                ) from e
            self._mt5 = mt5
        return self._mt5

    def connect(self) -> ConnectionStatus:
        """
        Initialize the MT5 terminal connection and log into the account.
        Safe to call again if already connected (no-op).
        """
        if self._connected:
            return ConnectionStatus(
                connected=True,
                account_login=self.settings.login,
                server=self.settings.server,
                message="already connected",
            )

        init_kwargs = {}
        if self.settings.terminal_path:
            init_kwargs["path"] = self.settings.terminal_path

        if not self.mt5.initialize(**init_kwargs):
            error = self.mt5.last_error()
            raise MT5ConnectionError(f"MT5 initialize() failed: {error}")

        if self.settings.login and self.settings.password and self.settings.server:
            authorized = self.mt5.login(
                login=self.settings.login,
                password=self.settings.password,
                server=self.settings.server,
            )
            if not authorized:
                error = self.mt5.last_error()
                self.mt5.shutdown()
                raise MT5ConnectionError(f"MT5 login() failed: {error}")

        self._connected = True
        return ConnectionStatus(
            connected=True,
            account_login=self.settings.login,
            server=self.settings.server,
            message="connected",
        )

    def disconnect(self) -> None:
        if self._connected:
            self.mt5.shutdown()
            self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def __enter__(self) -> "MT5Connector":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.disconnect()
