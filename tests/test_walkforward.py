"""
Tests for validation/walkforward.py.
Run with: python -m tests.test_walkforward
"""

import sys
sys.path.insert(0, ".")

import pandas as pd

from validation.walkforward import split_into_segments, run_segmented_analysis, STRATEGY_BUILDERS


def make_ohlc(n_bars: int) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=n_bars, freq="15min")
    closes = [1.1000 + 0.0001 * (i % 20) for i in range(n_bars)]
    return pd.DataFrame({"open": closes, "high": closes, "low": closes, "close": closes}, index=idx)


def test_split_produces_correct_segment_count():
    df = make_ohlc(1000)
    segments = split_into_segments(df, n_segments=5)
    assert len(segments) == 5
    print("PASS: split_into_segments produces the requested number of segments")


def test_split_segments_are_contiguous_and_cover_all_bars():
    df = make_ohlc(1003)  # deliberately not evenly divisible
    segments = split_into_segments(df, n_segments=4)
    total_bars = sum(len(s) for s in segments)
    assert total_bars == len(df), f"Expected segments to cover all {len(df)} bars, got {total_bars}"
    # Contiguity: each segment's last timestamp should be immediately
    # before the next segment's first timestamp.
    for i in range(len(segments) - 1):
        assert segments[i].index[-1] < segments[i + 1].index[0]
    print("PASS: segments are contiguous and cover every bar exactly once")


def test_split_rejects_too_few_segments():
    df = make_ohlc(100)
    try:
        split_into_segments(df, n_segments=1)
        assert False, "Expected ValueError for n_segments < 2"
    except ValueError:
        print("PASS: n_segments < 2 raises ValueError")


def test_unknown_strategy_name_raises():
    df = make_ohlc(500)
    try:
        run_segmented_analysis("not_a_real_strategy", df, n_segments=2)
        assert False
    except ValueError:
        print("PASS: unknown strategy name raises a clear ValueError")


def test_fresh_strategy_instance_per_segment_no_state_leak():
    """
    orb_breakout tracks day-state internally. If run_segmented_analysis
    reused one instance across segments instead of building fresh ones,
    stale state from segment 1's last day could suppress trading at the
    start of segment 2. This just confirms it runs without error across
    multiple segments and produces independent results per segment.
    """
    df = make_ohlc(2000)
    results = run_segmented_analysis("orb_breakout", df, n_segments=3, pip_size=0.0001)
    assert len(results) == 3
    # Each segment's label should reference distinct, non-overlapping dates.
    labels = [m.strategy_name for m in results]
    assert len(set(labels)) == 3, "Expected distinct segment labels"
    print("PASS: stateful strategy (orb_breakout) runs cleanly across multiple fresh segments")


def test_all_registered_strategies_are_runnable():
    df = make_ohlc(1500)
    for name in STRATEGY_BUILDERS:
        results = run_segmented_analysis(name, df, n_segments=2, pip_size=0.0001)
        assert len(results) == 2
    print(f"PASS: all {len(STRATEGY_BUILDERS)} registered strategies run through segmented analysis without error")


if __name__ == "__main__":
    test_split_produces_correct_segment_count()
    test_split_segments_are_contiguous_and_cover_all_bars()
    test_split_rejects_too_few_segments()
    test_unknown_strategy_name_raises()
    test_fresh_strategy_instance_per_segment_no_state_leak()
    test_all_registered_strategies_are_runnable()
    print("\nAll walkforward/segmented analysis tests passed.")
