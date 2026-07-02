"""
Conversion between MT5 broker server time and true UTC.

Every timestamp coming out of data/market_data.py (bar times, tick
times) is in the broker's server clock, NOT true UTC — see
config/settings.py::BrokerServerClock for how that offset was measured
and why it will drift with DST. Any strategy logic that cares about a
real-world session boundary (London open = 08:00 UTC, NY open = 13:00
UTC, etc.) must convert through this module rather than comparing
broker-server timestamps directly against UTC-based assumptions.
"""

from datetime import datetime, timedelta

from config.settings import BrokerServerClock, BROKER_SERVER_CLOCK


def broker_time_to_utc(server_time: datetime, clock: BrokerServerClock = BROKER_SERVER_CLOCK) -> datetime:
    """Convert a naive broker-server-clock datetime to naive true UTC."""
    return server_time - timedelta(hours=clock.utc_offset_hours)


def utc_to_broker_time(utc_time: datetime, clock: BrokerServerClock = BROKER_SERVER_CLOCK) -> datetime:
    """Convert a naive true-UTC datetime to the naive broker-server-clock equivalent."""
    return utc_time + timedelta(hours=clock.utc_offset_hours)
