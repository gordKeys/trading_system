from data.mt5_connector import MT5Connector
from data.market_data import fetch_ohlc, fetch_latest_tick, Timeframe
from data.symbol_info import get_symbol_info

with MT5Connector() as conn:
    print("Connected:", conn.is_connected())

    info = get_symbol_info(conn, "EURUSD")
    print("Symbol info:", info)

    tick = fetch_latest_tick(conn, "EURUSD")
    print("Latest tick:", tick)

    df = fetch_ohlc(conn, "EURUSD", Timeframe.M15, count=10)
    print(df)