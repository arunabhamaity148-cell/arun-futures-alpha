"""Tests for rolling statistics — O(1) per update, exact window."""
import math

import pytest

from trader_arun.core.rolling import (
    EWMA, RollingMean, RollingQuantile, RollingVariance, RollingZScore, safe_zscore,
)


def test_rolling_mean_basic():
    rm = RollingMean(maxlen=5)
    for x in [1, 2, 3, 4, 5]:
        rm.update(x)
    assert rm.mean == pytest.approx(3.0)
    assert rm.count == 5


def test_rolling_mean_window_evicts_old():
    rm = RollingMean(maxlen=3)
    for x in [10, 20, 30, 40, 50]:
        rm.update(x)
    assert rm.mean == pytest.approx(40.0)  # mean of [30, 40, 50]
    assert rm.count == 3


def test_rolling_variance_welford():
    rv = RollingVariance(maxlen=10)
    for x in [1, 2, 3, 4, 5]:
        rv.update(x)
    # Variance of [1..5] = 2.5
    assert rv.variance == pytest.approx(2.5, rel=1e-6)
    assert rv.std == pytest.approx(math.sqrt(2.5), rel=1e-6)
    assert rv.mean == pytest.approx(3.0)


def test_rolling_variance_handles_nan():
    rv = RollingVariance(maxlen=5)
    rv.update(1.0)
    rv.update(float("nan"))
    rv.update(2.0)
    # NaN should be skipped; variance computed over real values.
    assert math.isfinite(rv.variance)


def test_ewma_halflife():
    e = EWMA(halflife=10.0)
    # First value initialises.
    e.update(100.0)
    assert e.value == 100.0
    # After many updates with same value, EWMA converges to that value.
    for _ in range(1000):
        e.update(50.0)
    assert e.value == pytest.approx(50.0, abs=0.5)


def test_rolling_zscore():
    z = RollingZScore(maxlen=20)
    for x in [1.0] * 20:
        z.update(x)
    # All same → std=0 → z=0
    assert z.update(1.0) == 0.0


def test_rolling_zscore_with_outlier():
    z = RollingZScore(maxlen=20)
    for x in range(20):
        z.update(float(x))
    # Next value far above the mean.
    z_val = z.update(100.0)
    assert z_val > 2.0


def test_rolling_quantile():
    q = RollingQuantile(n_bins=100, min_val=0.0, max_val=100.0)
    for x in range(100):
        q.update(float(x))
    assert q.quantile(0.5) == pytest.approx(50.0, abs=2.0)
    assert q.quantile(0.0) == pytest.approx(0.0, abs=2.0)
    assert q.quantile(1.0) == pytest.approx(99.0, abs=2.0)


def test_safe_zscore():
    assert safe_zscore(2.0, 0.0, 1.0) == 2.0
    assert safe_zscore(2.0, 0.0, 0.0) == 0.0  # zero std → fallback
    assert safe_zscore(float("nan"), 0.0, 1.0) == 0.0
