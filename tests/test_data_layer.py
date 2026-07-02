"""
Tests for the data layer, using a fake MT5 module instead of the real
`MetaTrader5` package (which only runs on Windows with a live terminal).

This proves the connection, symbol-info, and OHLC-fetching logic is
correct in isolation. It does NOT prove the real MT5 package behaves
exactly like this fake — run a manual smoke test on your machine once
you have a demo account connected (see bottom of this file).

Run with: python -m tests.test_data_layer
"""

import sys
import types
from datetime import datetime

sys.path.insert(0, ".")

import numpy as np

from data.mt5_connector import MT5Connector, MT5ConnectionError
from data.symbol_info import get_symbol_info
from data.market_data import fetch_ohlc, fetch_latest_tick, Timeframe
from config.settings import MT5Settings


class FakeSymbolInfo:
    def __init__(self, visible=True, point=0.00001, digits=5,
                 trade_tick_value=1.0, volume_min=0.01, volume_max=100.0,
                 volume_step=0.01, spread=12):
        self.visible = visible
        self.point = point
        self.digits = digits
        self.trade_tick_value = trade_tick_value
        self.volume_min = volume_min
        self.volume_max = volume_max
        self.volume_step = volume_step
        self.spread = spread


class FakeTick:
    def __init__(self, time, bid, ask, last):
        self.time = time
        self.bid = bid
        self.ask = ask
        self.last = last


def make_fake_mt5(*, init_ok=True, login_ok=True, symbol_info=None):
    """Build a minimal fake mimicking the MetaTrader5 module's surface."""
    fake = types.SimpleNamespace()
    fake.TIMEFRAME_M1 = 1
    fake.TIMEFRAME_M5 = 5
    fake.TIMEFRAME_M15 = 15
    fake.TIMEFRAME_M30 = 30
    fake.TIMEFRAME_H1 = 60
    fake.TIMEFRAME_H4 = 240
    fake.TIMEFRAME_D1 = 1440

    fake.initialize = lambda **kwargs: init_ok
    fake.login = lambda **kwargs: login_ok
    fake.shutdown = lambda: None
    fake.last_error = lambda: (1, "fake error")

    _symbol_info = symbol_info or FakeSymbolInfo()
    fake.symbol_info = lambda symbol: _symbol_info
    fake.symbol_select = lambda symbol, enable: True

    def fake_copy_rates_from_pos(symbol, timeframe, start, count):
        dtype = [
            ("time", "i8"), ("open", "f8"), ("high", "f8"), ("low", "f8"),
            ("close", "f8"), ("tick_volume", "i8"), ("spread", "i4"),
            ("real_volume", "i8"),
        ]
        base_time = 1_700_000_000
        arr = np.zeros(count, dtype=dtype)
        for i in range(count):
            arr[i] = (base_time + i * 60, 1.1, 1.101, 1.099, 1.1005, 100, 12, 0)
        return arr
    fake.copy_rates_from_pos = fake_copy_rates_from_pos

    fake.symbol_info_tick = lambda symbol: FakeTick(
        time=1_700_000_000, bid=1.1000, ask=1.1002, last=1.1001
    )

    return fake


def test_connect_success():
    fake_mt5 = make_fake_mt5()
    settings = MT5Settings(login=123, password="pw", server="Demo")
    connector = MT5Connector(settings=settings, mt5_module=fake_mt5)
    status = connector.connect()
    assert status.connected
    assert connector.is_connected()
    print("PASS: connect succeeds with valid fake credentials")


def test_connect_failure_raises():
    fake_mt5 = make_fake_mt5(login_ok=False)
    settings = MT5Settings(login=123, password="bad", server="Demo")
    connector = MT5Connector(settings=settings, mt5_module=fake_mt5)
    try:
        connector.connect()
        assert False, "Expected MT5ConnectionError"
    except MT5ConnectionError:
        print("PASS: failed login raises MT5ConnectionError")


def test_reconnect_is_noop():
    fake_mt5 = make_fake_mt5()
    connector = MT5Connector(settings=MT5Settings(login=1, password="p", server="s"), mt5_module=fake_mt5)
    connector.connect()
    status2 = connector.connect()
    assert status2.message == "already connected"
    print("PASS: calling connect() twice is a safe no-op")


def test_symbol_info_pip_calc_5digit():
    # 5-digit quoting: pip = 10 * point
    fake_mt5 = make_fake_mt5(symbol_info=FakeSymbolInfo(point=0.00001, digits=5, trade_tick_value=1.0))
    connector = MT5Connector(settings=MT5Settings(), mt5_module=fake_mt5)
    connector.connect()
    info = get_symbol_info(connector, "EURUSD")
    assert abs(info.pip_size - 0.0001) < 1e-9
    assert abs(info.pip_value_per_lot - 10.0) < 1e-9, f"Expected ~10.0, got {info.pip_value_per_lot}"
    print("PASS: 5-digit symbol pip size/value computed correctly")


def test_symbol_info_pip_calc_2digit():
    # 2-digit quoting (e.g. some JPY pairs at certain brokers): pip = 1 * point
    fake_mt5 = make_fake_mt5(symbol_info=FakeSymbolInfo(point=0.01, digits=2, trade_tick_value=6.5))
    connector = MT5Connector(settings=MT5Settings(), mt5_module=fake_mt5)
    connector.connect()
    info = get_symbol_info(connector, "USDJPY")
    assert abs(info.pip_size - 0.01) < 1e-9
    assert abs(info.pip_value_per_lot - 6.5) < 1e-9
    print("PASS: 2-digit symbol pip size/value computed correctly")


def test_symbol_not_visible_gets_selected():
    calls = {"selected": False}
    info_obj = FakeSymbolInfo(visible=False)
    fake_mt5 = make_fake_mt5(symbol_info=info_obj)

    def fake_select(symbol, enable):
        calls["selected"] = True
        info_obj.visible = True
        return True
    fake_mt5.symbol_select = fake_select

    connector = MT5Connector(settings=MT5Settings(), mt5_module=fake_mt5)
    connector.connect()
    get_symbol_info(connector, "EURUSD")
    assert calls["selected"], "Expected symbol_select to be called for a non-visible symbol"
    print("PASS: non-visible symbol gets auto-selected in Market Watch")


def test_fetch_ohlc_shape():
    fake_mt5 = make_fake_mt5()
    connector = MT5Connector(settings=MT5Settings(), mt5_module=fake_mt5)
    connector.connect()
    df = fetch_ohlc(connector, "EURUSD", Timeframe.M15, count=50)
    assert len(df) == 50
    assert list(df.columns) == ["open", "high", "low", "close", "tick_volume", "spread", "real_volume"]
    assert df.index.name == "time"
    print("PASS: fetch_ohlc returns correctly shaped DataFrame")


def test_fetch_latest_tick():
    fake_mt5 = make_fake_mt5()
    connector = MT5Connector(settings=MT5Settings(), mt5_module=fake_mt5)
    connector.connect()
    tick = fetch_latest_tick(connector, "EURUSD")
    assert tick.bid == 1.1000
    assert tick.ask == 1.1002
    print("PASS: fetch_latest_tick returns expected bid/ask")


if __name__ == "__main__":
    test_connect_success()
    test_connect_failure_raises()
    test_reconnect_is_noop()
    test_symbol_info_pip_calc_5digit()
    test_symbol_info_pip_calc_2digit()
    test_symbol_not_visible_gets_selected()
    test_fetch_ohlc_shape()
    test_fetch_latest_tick()
    print("\nAll data layer tests passed (against a fake MT5 — see docstring).")
