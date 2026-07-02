"""
Tests for broker server time <-> UTC conversion.
Run with: python -m tests.test_broker_time
"""

import sys
sys.path.insert(0, ".")

from datetime import datetime

from config.settings import BrokerServerClock
from data.broker_time import broker_time_to_utc, utc_to_broker_time


def test_broker_to_utc_matches_measured_offset():
    clock = BrokerServerClock(utc_offset_hours=3.0)
    server_time = datetime(2026, 7, 2, 6, 41, 15)
    utc_time = broker_time_to_utc(server_time, clock)
    assert utc_time == datetime(2026, 7, 2, 3, 41, 15)
    print("PASS: broker_time_to_utc matches the measured +3h offset")


def test_round_trip_is_identity():
    clock = BrokerServerClock(utc_offset_hours=3.0)
    original = datetime(2026, 7, 2, 8, 0, 0)
    round_tripped = broker_time_to_utc(utc_to_broker_time(original, clock), clock)
    assert round_tripped == original
    print("PASS: converting to broker time and back returns the original value")


def test_winter_offset_configurable():
    # DST caveat check: a +2h winter offset should behave independently
    # of the current default (+3h) — proves the offset isn't hardcoded
    # anywhere in the conversion logic itself.
    winter_clock = BrokerServerClock(utc_offset_hours=2.0)
    server_time = datetime(2026, 12, 1, 10, 0, 0)
    utc_time = broker_time_to_utc(server_time, winter_clock)
    assert utc_time == datetime(2026, 12, 1, 8, 0, 0)
    print("PASS: a different (e.g. winter DST) offset can be supplied and is respected")


if __name__ == "__main__":
    test_broker_to_utc_matches_measured_offset()
    test_round_trip_is_identity()
    test_winter_offset_configurable()
    print("\nAll broker time conversion tests passed.")
